"""
Instagram Reels uploader via Meta Graph API (resumable upload protocol).

No public video URL required — uploads video bytes directly to Instagram's CDN.

Setup (one-time):
  1. Go to developers.facebook.com → Create App → Business type
  2. Add "Instagram" product, connect your Instagram Business/Creator account
  3. Generate a long-lived User Access Token with permissions:
       instagram_basic, instagram_content_publish, pages_read_engagement
  4. Find your Instagram User ID: GET /me?fields=id,username&access_token=<token>
  5. Run: python -m pipeline setup  (enter token + user ID)

Token lasts 60 days. Refresh before expiry at:
  https://developers.facebook.com/tools/explorer/
"""
import time
from pathlib import Path

import requests

from pipeline.config import load_config
from pipeline.log import get_logger

log = get_logger("instagram")

_GRAPH = "https://graph.facebook.com/v19.0"


def is_configured() -> bool:
    cfg = load_config()
    return bool(cfg.get("INSTAGRAM_ACCESS_TOKEN")) and bool(cfg.get("INSTAGRAM_USER_ID"))


def _credentials() -> tuple[str, str]:
    cfg = load_config()
    token = cfg.get("INSTAGRAM_ACCESS_TOKEN", "")
    uid = cfg.get("INSTAGRAM_USER_ID", "")
    if not token or not uid:
        raise ValueError(
            "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID not set.\n"
            "Run: python -m pipeline setup"
        )
    return token, uid


def upload_reel(video_path: Path, caption: str) -> str:
    """
    Upload a video as an Instagram Reel.
    Returns the Instagram post permalink.
    """
    token, uid = _credentials()
    video_bytes = video_path.read_bytes()
    file_size = len(video_bytes)

    # Step 1: Create media container with resumable upload
    log.info("Creating Instagram media container...")
    resp = requests.post(
        f"{_GRAPH}/{uid}/media",
        params={"access_token": token},
        data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption,
        },
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Instagram container creation failed: {resp.text}")
    data = resp.json()
    container_id = data["id"]
    upload_uri = data.get("uri") or f"https://rupload.facebook.com/video-upload/v19.0/{container_id}"
    log.info(f"Container ID: {container_id}")

    # Step 2: Upload video bytes
    size_mb = file_size / 1024 / 1024
    log.info(f"Uploading video ({size_mb:.1f} MB) to Instagram CDN...")
    upload_resp = requests.post(
        upload_uri,
        headers={
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "application/octet-stream",
        },
        data=video_bytes,
        timeout=300,
    )
    if not upload_resp.ok:
        raise RuntimeError(f"Instagram video upload failed: {upload_resp.text}")
    log.info("Video bytes uploaded successfully")

    # Step 3: Poll until Instagram finishes processing
    log.info("Waiting for Instagram to process video...")
    for attempt in range(40):
        time.sleep(5)
        status_resp = requests.get(
            f"{_GRAPH}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=15,
        )
        status_data = status_resp.json()
        status_code = status_data.get("status_code", "")
        log.info(f"  Processing status: {status_code}")
        if status_code == "FINISHED":
            break
        if status_code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed: {status_data.get('status')}")
    else:
        raise RuntimeError("Instagram video processing timed out after 3.5 minutes")

    # Step 4: Publish
    log.info("Publishing Reel...")
    pub_resp = requests.post(
        f"{_GRAPH}/{uid}/media_publish",
        params={"access_token": token},
        data={"creation_id": container_id},
        timeout=30,
    )
    if not pub_resp.ok:
        raise RuntimeError(f"Instagram publish failed: {pub_resp.text}")
    media_id = pub_resp.json()["id"]

    # Get permalink
    try:
        link_resp = requests.get(
            f"{_GRAPH}/{media_id}",
            params={"fields": "permalink", "access_token": token},
            timeout=10,
        )
        permalink = link_resp.json().get("permalink", f"https://www.instagram.com/reel/{media_id}/")
    except Exception:
        permalink = f"https://www.instagram.com/reel/{media_id}/"

    log.info(f"Reel published: {permalink}")
    return permalink
