"""
YouTube OAuth2 setup script.
Run this once to authorize the pipeline to upload to your YouTube channel.
"""
import json
import stat
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".shorts-pipeline"
TOKEN_FILE = CONFIG_DIR / "youtube_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",           # needed for public visibility
    "https://www.googleapis.com/auth/youtube.force-ssl", # needed for captions
    "https://www.googleapis.com/auth/drive.readonly",    # needed for Drive folder upload
]


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials
    except ImportError:
        print("Missing dependencies. Run: pip install google-auth-oauthlib")
        sys.exit(1)

    print("=== YouTube OAuth2 Setup ===\n")
    print("You need a Google Cloud project with the YouTube Data API v3 enabled.")
    print("Download your OAuth2 client credentials (client_secrets.json) from:")
    print("  https://console.cloud.google.com/ → APIs & Services → Credentials\n")

    secrets_path = input("Path to client_secrets.json: ").strip()
    secrets_path = Path(secrets_path).expanduser()

    if not secrets_path.exists():
        print(f"File not found: {secrets_path}")
        sys.exit(1)

    print("\nOpening browser for authorization...")
    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
    creds = flow.run_local_server(port=0)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    tmp = TOKEN_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(token_data, f, indent=2)
    tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    tmp.rename(TOKEN_FILE)

    print(f"\nToken saved to: {TOKEN_FILE}")
    print("YouTube OAuth setup complete!\n")
    print("You can now run:")
    print("  python -m pipeline run --topic 'your topic'")


if __name__ == "__main__":
    main()
