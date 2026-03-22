#!/usr/bin/env python3
"""
Refresh the Instagram long-lived access token.
Long-lived tokens last 60 days; run this every 50 days via cron.
Cron: 0 9 */50 * * /path/to/.venv/bin/python /path/to/scripts/refresh_instagram_token.py
"""
import json
import pathlib
import requests
import sys
from datetime import datetime

CONFIG_PATH = pathlib.Path.home() / ".shorts-pipeline" / "config.json"


def refresh():
    cfg = json.loads(CONFIG_PATH.read_text())
    token = cfg.get("INSTAGRAM_ACCESS_TOKEN")
    app_id = cfg.get("FACEBOOK_APP_ID")
    app_secret = cfg.get("FACEBOOK_APP_SECRET")

    if not all([token, app_id, app_secret]):
        print("ERROR: Missing INSTAGRAM_ACCESS_TOKEN, FACEBOOK_APP_ID, or FACEBOOK_APP_SECRET in config.")
        sys.exit(1)

    r = requests.get(
        "https://graph.facebook.com/v19.0/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": token,
        },
        timeout=15,
    )
    data = r.json()

    if "access_token" not in data:
        print(f"ERROR: Token refresh failed: {data}")
        sys.exit(1)

    cfg["INSTAGRAM_ACCESS_TOKEN"] = data["access_token"]
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    CONFIG_PATH.chmod(0o600)
    print(f"[{datetime.now().isoformat()}] Instagram token refreshed successfully.")


if __name__ == "__main__":
    refresh()
