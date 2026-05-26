#!/usr/bin/env bash
# =============================================================================
# deploy.sh — ECS Fargate + ALB deployment for jira-triage-agent
#
# Prerequisites:
#   - AWS CLI configured (aws configure) with sufficient permissions
#   - Docker running locally
#   - .env file present in project root with real values
#
# Usage:
#   cd infra && bash deploy.sh
# =============================================================================
set -euo pipefail

# ── 0. CONFIG — edit these ────────────────────────────────────────────────────
APP_NAME="jira-triage-agent"
REGION="us-east-1"               # change to your preferred region
CONTAINER_PORT=8501
TASK_CPU=512                     # 0.5 vCPU
TASK_MEMORY=1024                 # 1 GB
DESIRED_COUNT=1

# VPC — leave blank to use the default VPC
VPC_ID=""
# Subnets — leave blank to auto-detect public subnets from default VPC
SUBNET_IDS=""
# =============================================================================

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo ""
echo "============================================================"
echo " Deploying: $APP_NAME  →  ECS Fargate + ALB"
echo " Region   : $REGION"
echo "============================================================"

# ── 1. Account ID ─────────────────────────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "[1/9] AWS Account: $ACCOUNT_ID"

# ── 2. VPC / Subnets (auto-detect default VPC if not set) ────────────────────
if [[ -z "$VPC_ID" ]]; then
  VPC_ID=$(aws ec2 describe-vpcs \
    --filters Name=isDefault,Values=true \
    --query "Vpcs[0].VpcId" --output text --region "$REGION")
fi
echo "[2/9] VPC: $VPC_ID"

if [[ -z "$SUBNET_IDS" ]]; then
  SUBNET_IDS=$(aws ec2 describe-subnets \
    --filters Name=vpc-id,Values="$VPC_ID" Name=defaultForAz,Values=true \
    --query "Subnets[*].SubnetId" --output text --region "$REGION" | tr '\t' ',')
fi
echo "      Subnets: $SUBNET_IDS"

# ── 3. ECR — create repo & push image ────────────────────────────────────────
echo "[3/9] ECR — creating repo (if needed) and pushing image..."
aws ecr describe-repositories --repository-names "$APP_NAME" \
  --region "$REGION" &>/dev/null \
  || aws ecr create-repository --repository-name "$APP_NAME" \
       --region "$REGION" --query "repository.repositoryUri" --output text

ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$APP_NAME"

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

docker buildx build --platform linux/amd64 \
  -t "$ECR_URI:latest" \
  --push \
  "$PROJECT_ROOT"
echo "      Pushed: $ECR_URI:latest"

# ── 4. Secrets Manager — store all .env values as one JSON secret ─────────────
echo "[4/9] Secrets Manager — writing secrets..."
SECRET_NAME="$APP_NAME"
SECRET_JSON=$(python3 - <<'PYEOF'
import os, json
from pathlib import Path

env_file = Path(__file__).parent.parent / ".env"
data = {}
for line in env_file.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        data[k.strip()] = v.strip()
print(json.dumps(data))
PYEOF
)

if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" \
     --region "$REGION" &>/dev/null; then
  aws secretsmanager update-secret \
    --secret-id "$SECRET_NAME" \
    --secret-string "$SECRET_JSON" \
    --region "$REGION" > /dev/null
  echo "      Updated existing secret."
else
  aws secretsmanager create-secret \
    --name "$SECRET_NAME" \
    --secret-string "$SECRET_JSON" \
    --region "$REGION" > /dev/null
  echo "      Created new secret."
fi

SECRET_ARN=$(aws secretsmanager describe-secret \
  --secret-id "$SECRET_NAME" \
  --query "ARN" --output text --region "$REGION")

# ── 5. IAM — ensure ecsTaskExecutionRole can read the secret ─────────────────
echo "[5/9] IAM — attaching SecretsManager policy to ecsTaskExecutionRole..."
aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/SecretsManagerReadWrite 2>/dev/null || true
aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy 2>/dev/null || true

# ── 6. CloudWatch Logs ────────────────────────────────────────────────────────
echo "[6/9] CloudWatch — creating log group..."
aws logs create-log-group \
  --log-group-name "/ecs/$APP_NAME" \
  --region "$REGION" 2>/dev/null || true

# ── 7. Security Groups ────────────────────────────────────────────────────────
echo "[7/9] Security groups..."

# ALB security group — allow HTTP/HTTPS from anywhere
ALB_SG_ID=$(aws ec2 describe-security-groups \
  --filters Name=group-name,Values="$APP_NAME-alb" Name=vpc-id,Values="$VPC_ID" \
  --query "SecurityGroups[0].GroupId" --output text --region "$REGION" 2>/dev/null || echo "None")

if [[ "$ALB_SG_ID" == "None" ]]; then
  ALB_SG_ID=$(aws ec2 create-security-group \
    --group-name "$APP_NAME-alb" \
    --description "ALB SG for $APP_NAME" \
    --vpc-id "$VPC_ID" \
    --region "$REGION" \
    --query "GroupId" --output text)
  aws ec2 authorize-security-group-ingress --group-id "$ALB_SG_ID" \
    --protocol tcp --port 80 --cidr 0.0.0.0/0 --region "$REGION"
  aws ec2 authorize-security-group-ingress --group-id "$ALB_SG_ID" \
    --protocol tcp --port 443 --cidr 0.0.0.0/0 --region "$REGION"
fi

# ECS task security group — allow traffic only from ALB SG
TASK_SG_ID=$(aws ec2 describe-security-groups \
  --filters Name=group-name,Values="$APP_NAME-ecs" Name=vpc-id,Values="$VPC_ID" \
  --query "SecurityGroups[0].GroupId" --output text --region "$REGION" 2>/dev/null || echo "None")

if [[ "$TASK_SG_ID" == "None" ]]; then
  TASK_SG_ID=$(aws ec2 create-security-group \
    --group-name "$APP_NAME-ecs" \
    --description "ECS task SG for $APP_NAME" \
    --vpc-id "$VPC_ID" \
    --region "$REGION" \
    --query "GroupId" --output text)
  aws ec2 authorize-security-group-ingress --group-id "$TASK_SG_ID" \
    --protocol tcp --port "$CONTAINER_PORT" \
    --source-group "$ALB_SG_ID" --region "$REGION"
fi
echo "      ALB SG : $ALB_SG_ID"
echo "      Task SG: $TASK_SG_ID"

# ── 8. ALB + Target Group + Listener ─────────────────────────────────────────
echo "[8/9] ALB..."
SUBNET_LIST="${SUBNET_IDS//,/ }"  # space-separated for ALB creation

ALB_ARN=$(aws elbv2 describe-load-balancers \
  --names "$APP_NAME-alb" --region "$REGION" \
  --query "LoadBalancers[0].LoadBalancerArn" --output text 2>/dev/null || echo "None")

if [[ "$ALB_ARN" == "None" ]]; then
  ALB_ARN=$(aws elbv2 create-load-balancer \
    --name "$APP_NAME-alb" \
    --subnets $SUBNET_LIST \
    --security-groups "$ALB_SG_ID" \
    --scheme internet-facing \
    --type application \
    --region "$REGION" \
    --query "LoadBalancers[0].LoadBalancerArn" --output text)
fi

TG_ARN=$(aws elbv2 describe-target-groups \
  --names "$APP_NAME-tg" --region "$REGION" \
  --query "TargetGroups[0].TargetGroupArn" --output text 2>/dev/null || echo "None")

if [[ "$TG_ARN" == "None" ]]; then
  TG_ARN=$(aws elbv2 create-target-group \
    --name "$APP_NAME-tg" \
    --protocol HTTP \
    --port "$CONTAINER_PORT" \
    --vpc-id "$VPC_ID" \
    --target-type ip \
    --health-check-path "/_stcore/health" \
    --health-check-interval-seconds 30 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --region "$REGION" \
    --query "TargetGroups[0].TargetGroupArn" --output text)
fi

# HTTP listener (port 80) — no ACM cert yet; for HTTPS add ACM cert ARN below
LISTENER_ARN=$(aws elbv2 describe-listeners \
  --load-balancer-arn "$ALB_ARN" --region "$REGION" \
  --query "Listeners[?Port==\`80\`].ListenerArn" --output text 2>/dev/null)

if [[ -z "$LISTENER_ARN" ]]; then
  aws elbv2 create-listener \
    --load-balancer-arn "$ALB_ARN" \
    --protocol HTTP --port 80 \
    --default-actions Type=forward,TargetGroupArn="$TG_ARN" \
    --region "$REGION" > /dev/null
fi

ALB_DNS=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns "$ALB_ARN" \
  --query "LoadBalancers[0].DNSName" --output text --region "$REGION")

# ── 9. ECS Cluster + Task Definition + Service ───────────────────────────────
echo "[9/9] ECS cluster + service..."

aws ecs create-cluster \
  --cluster-name "$APP_NAME" \
  --region "$REGION" > /dev/null 2>&1 || true

# Render task definition (substitute placeholders)
TASK_DEF_FILE="$(mktemp /tmp/task-def-XXXX.json)"
sed -e "s/__ACCOUNT_ID__/$ACCOUNT_ID/g" \
    -e "s/__REGION__/$REGION/g" \
    "$PROJECT_ROOT/infra/task-definition.json" > "$TASK_DEF_FILE"

TASK_DEF_ARN=$(aws ecs register-task-definition \
  --cli-input-json "file://$TASK_DEF_FILE" \
  --region "$REGION" \
  --query "taskDefinition.taskDefinitionArn" --output text)
rm -f "$TASK_DEF_FILE"

# Create or update service
SERVICE_EXISTS=$(aws ecs describe-services \
  --cluster "$APP_NAME" --services "$APP_NAME" \
  --region "$REGION" \
  --query "services[?status=='ACTIVE'].serviceName" --output text 2>/dev/null)

if [[ -z "$SERVICE_EXISTS" ]]; then
  aws ecs create-service \
    --cluster "$APP_NAME" \
    --service-name "$APP_NAME" \
    --task-definition "$TASK_DEF_ARN" \
    --desired-count "$DESIRED_COUNT" \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_IDS],securityGroups=[$TASK_SG_ID],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=$TG_ARN,containerName=$APP_NAME,containerPort=$CONTAINER_PORT" \
    --region "$REGION" > /dev/null
  echo "      Service created."
else
  aws ecs update-service \
    --cluster "$APP_NAME" \
    --service "$APP_NAME" \
    --task-definition "$TASK_DEF_ARN" \
    --force-new-deployment \
    --region "$REGION" > /dev/null
  echo "      Service updated (rolling deploy started)."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Deployment complete!"
echo " App URL  : http://$ALB_DNS"
echo ""
echo " NOTE: It takes ~2 minutes for the ECS task to become healthy."
echo " Watch:  aws ecs describe-services --cluster $APP_NAME --services $APP_NAME --region $REGION"
echo ""
echo " HTTPS:  Request an ACM certificate for your domain, then"
echo "         add an HTTPS:443 listener on the ALB pointing to the"
echo "         same target group, and add a Route53 CNAME/alias."
echo "============================================================"
