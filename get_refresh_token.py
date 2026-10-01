"""Run ONCE on your own computer: python get_refresh_token.py
Needs client_secret.json (OAuth 'Desktop app' credentials from Google Cloud Console)."""
from google_auth_oauthlib.flow import InstalledAppFlow
from yt_auth import SCOPES

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nYT_CLIENT_ID     =", creds.client_id)
print("YT_CLIENT_SECRET =", creds.client_secret)
print("YT_REFRESH_TOKEN =", creds.refresh_token)
print("\nAdd these three as GitHub repo secrets. Never commit them.")
