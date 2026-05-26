import os

# Must be set BEFORE any src module is imported, because several modules
# read os.environ at module level.
os.environ.setdefault("JIRA_BASE_URL", "https://netradyne.atlassian.net")
os.environ.setdefault("JIRA_EMAIL", "test@netradyne.com")
os.environ.setdefault("JIRA_API_TOKEN", "dummy-jira-token")
os.environ.setdefault("OPENAI_API_KEY", "sk-dummy-openai")
os.environ.setdefault("PINECONE_API_KEY", "dummy-pinecone-key")
