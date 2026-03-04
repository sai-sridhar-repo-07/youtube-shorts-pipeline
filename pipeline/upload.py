from pathlib import Path

from pipeline.config import CONFIG_DIR
from pipeline.log import get_logger
from pipeline.retry import with_retry

log = get_logger("upload")

YOUTUBE_TOKEN = CONFIG_DIR / "youtube_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def _get_youtube_client():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    if not YOUTUBE_TOKEN.exists():
        raise FileNotFoundError(
            f"YouTube token not found at {YOUTUBE_TOKEN}.\n"
            "Run: python scripts/setup_youtube_oauth.py"
        )

    creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN), SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token
        YOUTUBE_TOKEN.write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


@with_retry(max_retries=2, delay=5)
def upload_to_youtube(
    video: Path,
    draft: dict,
    captions_srt: Path | None = None,
    thumbnail: Path | None = None,
) -> str:
    from googleapiclient.http import MediaFileUpload

    youtube = _get_youtube_client()

    title = draft.get("youtube_title", "YouTube Short")[:100]
    description = draft.get("youtube_description", "")
    tags = draft.get("youtube_tags", [])
    if isinstance(tags, list):
        tags = tags[:500]

    # Add #Shorts to description for YouTube Shorts algorithm
    if "#Shorts" not in description:
        description = description + "\n\n#Shorts"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    log.info(f"Uploading video: {video.name}")
    media = MediaFileUpload(str(video), mimetype="video/mp4", resumable=True, chunksize=1024 * 1024)

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    video_id = None
    while video_id is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            log.info(f"Upload progress: {pct}%")
        if response:
            video_id = response["id"]

    log.info(f"Video uploaded: https://youtu.be/{video_id}")

    # Upload captions
    if captions_srt and captions_srt.exists() and captions_srt.stat().st_size > 0:
        try:
            log.info("Uploading SRT captions...")
            media_captions = MediaFileUpload(str(captions_srt), mimetype="application/octet-stream")
            youtube.captions().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "language": "en",
                        "name": "English",
                        "isDraft": False,
                    }
                },
                media_body=media_captions,
            ).execute()
            log.info("Captions uploaded")
        except Exception as e:
            log.warning(f"Caption upload failed (non-fatal): {e}")

    # Upload thumbnail
    if thumbnail and thumbnail.exists():
        try:
            log.info("Uploading thumbnail...")
            media_thumb = MediaFileUpload(str(thumbnail), mimetype="image/png")
            youtube.thumbnails().set(videoId=video_id, media_body=media_thumb).execute()
            log.info("Thumbnail uploaded")
        except Exception as e:
            log.warning(f"Thumbnail upload failed (non-fatal): {e}")

    return f"https://youtu.be/{video_id}"
