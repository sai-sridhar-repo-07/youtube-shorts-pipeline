"""
Google Drive → YouTube uploader.

Downloads every video from a Drive folder and uploads to YouTube as a public Short.
All videos share a single caption (title/description/tags) — no Gemini analysis needed.
No captions, no music, no voiceover — just your original video.

Usage:
    python -m pipeline drive --folder <drive-folder-url-or-id>
    python -m pipeline drive --folder <url> --limit 5
    python -m pipeline drive --folder <url> --caption "My Animation #Shorts"
"""
import re
import tempfile
from pathlib import Path

from pipeline.config import CONFIG_DIR
from pipeline.log import get_logger
from pipeline.upload import upload_to_youtube
from pipeline.instagram_upload import upload_reel as instagram_upload_reel, is_configured as instagram_configured

log = get_logger("drive_upload")

# Tracking file lives in the repo so GitHub Actions remembers uploads across runs
_UPLOADED_LOG = Path(__file__).parent.parent / "data" / "drive_uploaded.txt"

# Supported video extensions on Drive
VIDEO_MIME_TYPES = [
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
    "video/webm",
    "video/mpeg",
    "video/3gpp",
]

# Track uploaded Drive files to avoid duplicates


def _extract_folder_id(folder_url_or_id: str) -> str:
    """Accept a Drive folder URL or raw ID and return just the folder ID."""
    # https://drive.google.com/drive/folders/<ID>
    m = re.search(r"/folders/([a-zA-Z0-9_-]+)", folder_url_or_id)
    if m:
        return m.group(1)
    # https://drive.google.com/drive/u/0/folders/<ID>
    m = re.search(r"id=([a-zA-Z0-9_-]+)", folder_url_or_id)
    if m:
        return m.group(1)
    # assume it's already a raw ID
    return folder_url_or_id.strip()


def _get_drive_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    token_path = CONFIG_DIR / "youtube_token.json"
    if not token_path.exists():
        raise FileNotFoundError(
            f"Token not found at {token_path}.\n"
            "Run: python scripts/setup_youtube_oauth.py"
        )
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    ]
    creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _list_drive_videos(folder_id: str) -> list[dict]:
    """Return list of {id, name, mimeType} for all videos in the folder."""
    drive = _get_drive_service()
    mime_filter = " or ".join(f"mimeType='{m}'" for m in VIDEO_MIME_TYPES)
    query = f"'{folder_id}' in parents and ({mime_filter}) and trashed=false"

    videos = []
    page_token = None
    while True:
        resp = drive.files().list(
            q=query,
            fields="nextPageToken, files(id, name, mimeType, size)",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        videos.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    log.info(f"Found {len(videos)} video(s) in Drive folder")
    return videos


def _already_uploaded(file_id: str) -> bool:
    if not _UPLOADED_LOG.exists():
        return False
    return file_id in _UPLOADED_LOG.read_text().splitlines()


def _mark_uploaded(file_id: str) -> None:
    _UPLOADED_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_UPLOADED_LOG, "a") as f:
        f.write(file_id + "\n")


def _download_drive_file(file_id: str, dest: Path) -> None:
    """Download a Drive file by ID to dest path."""
    from googleapiclient.http import MediaIoBaseDownload
    import io

    drive = _get_drive_service()
    request = drive.files().get_media(fileId=file_id)
    with open(dest, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                log.info(f"  Download progress: {pct}%")


_DEFAULT_CAPTION = "Amazing Animation 🎨 #Shorts"
_DEFAULT_DESCRIPTION = "Stunning animation you won't forget! 🎬\n\n#Shorts #Animation #Art #Viral #Trending"
_DEFAULT_TAGS = ["shorts", "animation", "art", "viral", "trending", "satisfying", "creative"]


def upload_drive_folder(folder_url: str, limit: int = 0, skip_uploaded: bool = True, caption: str = "") -> list[str]:
    """
    Main entry: download all videos from a Drive folder and upload to YouTube.
    Returns list of YouTube URLs.
    """
    folder_id = _extract_folder_id(folder_url)
    log.info(f"Drive folder ID: {folder_id}")

    videos = _list_drive_videos(folder_id)

    title = caption.strip() if caption.strip() else _DEFAULT_CAPTION
    draft = {
        "youtube_title": title[:100],
        "youtube_description": _DEFAULT_DESCRIPTION,
        "youtube_tags": _DEFAULT_TAGS,
    }
    log.info(f"Using caption for all videos: \"{title}\"")

    urls = []
    uploaded_count = 0
    for i, video_file in enumerate(videos, 1):
        if limit and uploaded_count >= limit:
            break

        file_id = video_file["id"]
        name = video_file["name"]
        log.info(f"\n[{i}/{len(videos)}] Processing: {name}")

        if skip_uploaded and _already_uploaded(file_id):
            log.info(f"  Already uploaded, skipping")
            continue

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            video_path = tmp / name

            # 1. Download
            log.info(f"  Downloading from Drive...")
            try:
                _download_drive_file(file_id, video_path)
            except Exception as e:
                log.warning(f"  Download failed: {e} — skipping")
                continue

            # 2. Upload to YouTube (same caption for all videos)
            log.info(f"  Uploading to YouTube...")
            try:
                url = upload_to_youtube(
                    video=video_path,
                    draft=draft,
                    captions_srt=None,
                    thumbnail=None,
                )
                urls.append(url)
                _mark_uploaded(file_id)
                uploaded_count += 1
                log.info(f"  Uploaded: {url}")
                print(f"\n✓ [{i}/{len(videos)}] {title}\n  YouTube: {url}")
            except Exception as e:
                log.warning(f"  YouTube upload failed: {e}")
                continue

            # 3. Upload to Instagram (if configured)
            if instagram_configured():
                log.info(f"  Uploading to Instagram...")
                try:
                    ig_caption = f"{title}\n\n#Shorts #Animation #Art #Viral #Trending"
                    ig_url = instagram_upload_reel(video_path, ig_caption)
                    log.info(f"  Instagram: {ig_url}")
                    print(f"  Instagram: {ig_url}")
                except Exception as e:
                    log.warning(f"  Instagram upload failed (non-fatal): {e}")

    return urls
