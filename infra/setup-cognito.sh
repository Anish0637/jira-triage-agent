#!/usr/bin/env bash
# =============================================================================
# setup-cognito.sh — Create Cognito User Pool for jira-triage-agent
#
# Usage:
#   AWS_PROFILE=anish0637 AWS_DEFAULT_REGION=us-east-1 bash infra/setup-cognito.sh
#
# After running, adds COGNITO_USER_POOL_ID and COGNITO_CLIENT_ID to
# Secrets Manager and prints commands to create/invite users.
# =============================================================================
set -euo pipefail

APP_NAME="jira-triage-agent"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo ""
echo "============================================================"
echo " Setting up Cognito for: $APP_NAME"
echo " Region: $REGION"
echo "============================================================"

# ── 1. Create User Pool ───────────────────────────────────────────────────────
echo "[1/4] Creating User Pool..."
USER_POOL_ID=$(aws cognito-idp create-user-pool \
  --pool-name "$APP_NAME-users" \
  --policies "PasswordPolicy={MinimumLength=8,RequireUppercase=true,RequireLowercase=true,RequireNumbers=true,RequireSymbols=false}" \
  --auto-verified-attributes email \
  --username-attributes email \
  --admin-create-user-config "AllowAdminCreateUserOnly=true" \
  --region "$REGION" \
  --query "UserPool.Id" --output text)

echo "      User Pool ID: $USER_POOL_ID"

# ── 2. Create App Client (no secret — for direct auth from Python) ────────────
echo "[2/4] Creating App Client..."
CLIENT_ID=$(aws cognito-idp create-user-pool-client \
  --user-pool-id "$USER_POOL_ID" \
  --client-name "$APP_NAME-client" \
  --no-generate-secret \
  --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH ALLOW_USER_SRP_AUTH \
  --token-validity-units "AccessToken=hours,IdToken=hours,RefreshToken=days" \
  --access-token-validity 8 \
  --id-token-validity 8 \
  --refresh-token-validity 30 \
  --region "$REGION" \
  --query "UserPoolClient.ClientId" --output text)

echo "      Client ID: $CLIENT_ID"

# ── 3. Inject into Secrets Manager ───────────────────────────────────────────
echo "[3/4] Updating Secrets Manager..."
CURRENT=$(aws secretsmanager get-secret-value \
  --secret-id "$APP_NAME" --query SecretString --output text --region "$REGION")

python3 - <<PYEOF
import json
d = json.loads('''$CURRENT''')
d['COGNITO_USER_POOL_ID'] = '$USER_POOL_ID'
d['COGNITO_CLIENT_ID']    = '$CLIENT_ID'
d['COGNITO_REGION']       = '$REGION'
with open('/tmp/updated-secret.json', 'w') as f:
    json.dump(d, f)
PYEOF

aws secretsmanager update-secret \
  --secret-id "$APP_NAME" \
  --secret-string "file:///tmp/updated-secret.json" \
  --region "$REGION" --query "Name" --output text
rm -f /tmp/updated-secret.json

# ── 4. Create first admin user ────────────────────────────────────────────────
echo "[4/4] Creating admin user..."
echo -n "  Enter admin email: "
read ADMIN_EMAIL

aws cognito-idp admin-create-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "$ADMIN_EMAIL" \
  --temporary-password "Triage1234!" \
  --user-attributes Name=email,Value="$ADMIN_EMAIL" Name=email_verified,Value=true \
  --message-action SUPPRESS \
  --region "$REGION" > /dev/null

echo ""
echo "============================================================"
echo " Done!"
echo " User Pool ID : $USER_POOL_ID"
echo " Client ID    : $CLIENT_ID"
echo ""
echo " Admin user   : $ADMIN_EMAIL"
echo " Temp password: Triage1234!"
echo " (You will be prompted to set a new password on first login)"
echo ""
echo " To add more users:"
echo "   aws cognito-idp admin-create-user \\"
echo "     --user-pool-id $USER_POOL_ID \\"
echo "     --username user@example.com \\"
echo "     --temporary-password 'Triage1234!' \\"
echo "     --user-attributes Name=email,Value=user@example.com Name=email_verified,Value=true \\"
echo "     --message-action SUPPRESS \\"
echo "     --region $REGION"
echo ""
echo " Now rebuild and redeploy:"
echo "   AWS_PROFILE=anish0637 AWS_DEFAULT_REGION=us-east-1 bash infra/deploy.sh"
echo "============================================================"
