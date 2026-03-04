"""
Google Drive → YouTube uploader.

Downloads every video from a Drive folder, analyzes each one with Gemini
to generate a title/description/tags, then uploads to YouTube as a public Short.
No captions, no music, no voiceover — just your original video.

Usage:
    python -m pipeline drive --folder <drive-folder-url-or-id>
    python -m pipeline drive --folder <url> --limit 5   # only first 5 videos
"""
import re
import subprocess
import tempfile
from pathlib import Path

from pipeline.config import load_config, CONFIG_DIR
from pipeline.log import get_logger
from pipeline.upload import upload_to_youtube

log = get_logger("drive_upload")

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
_UPLOADED_LOG = CONFIG_DIR / "drive_uploaded.txt"


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
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
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


def _extract_middle_frame(video_path: Path, out_path: Path) -> bool:
    """Extract a frame from the middle of the video for Gemini analysis."""
    # Get duration
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
        capture_output=True, text=True,
    )
    try:
        duration = float(result.stdout.strip())
    except ValueError:
        duration = 5.0
    seek = max(0, duration / 2)

    result = subprocess.run(
        ["ffmpeg", "-y", "-ss", str(seek), "-i", str(video_path),
         "-frames:v", "1", "-q:v", "2", str(out_path)],
        capture_output=True,
    )
    return out_path.exists()


def _analyze_video_with_gemini(frame_path: Path, filename: str) -> dict:
    """Send a frame to Gemini and get back title, description, tags."""
    import base64
    import json as _json
    import google.generativeai as genai

    cfg = load_config()
    api_key = cfg.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in config")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    image_data = base64.b64encode(frame_path.read_bytes()).decode()

    prompt = f"""You are a YouTube Shorts expert. Analyze this video frame (from a video named "{filename}") and generate metadata for uploading it as a YouTube Short.

Return ONLY valid JSON with these exact keys:
{{
  "youtube_title": "Catchy title under 100 characters that will get clicks",
  "youtube_description": "Engaging 2-3 sentence description. End with relevant hashtags.",
  "youtube_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
}}

Rules:
- Title must be under 100 characters
- Make it curiosity-driven and engaging
- Tags should be relevant to the video content
- Description should end with #Shorts"""

    response = model.generate_content([
        {"mime_type": "image/jpeg", "data": image_data},
        prompt,
    ])

    text = response.text.strip()
    # Strip markdown fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = _json.loads(text)
    except Exception:
        log.warning(f"Gemini returned invalid JSON, using filename as title")
        name = Path(filename).stem.replace("_", " ").replace("-", " ").title()
        data = {
            "youtube_title": name[:100],
            "youtube_description": f"{name}\n\n#Shorts",
            "youtube_tags": ["shorts", "viral", "trending"],
        }

    return data


def upload_drive_folder(folder_url: str, limit: int = 0, skip_uploaded: bool = True) -> list[str]:
    """
    Main entry: download all videos from a Drive folder and upload to YouTube.
    Returns list of YouTube URLs.
    """
    folder_id = _extract_folder_id(folder_url)
    log.info(f"Drive folder ID: {folder_id}")

    videos = _list_drive_videos(folder_id)
    if limit:
        videos = videos[:limit]

    urls = []
    for i, video_file in enumerate(videos, 1):
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

            # 2. Analyze with Gemini
            log.info(f"  Analyzing video with Gemini...")
            draft = {}
            frame_path = tmp / "frame.jpg"
            try:
                if _extract_middle_frame(video_path, frame_path):
                    draft = _analyze_video_with_gemini(frame_path, name)
                    log.info(f"  Title: {draft.get('youtube_title')}")
                else:
                    raise RuntimeError("Frame extraction failed")
            except Exception as e:
                log.warning(f"  Gemini analysis failed: {e} — using filename as title")
                clean_name = Path(name).stem.replace("_", " ").replace("-", " ").title()
                draft = {
                    "youtube_title": clean_name[:100],
                    "youtube_description": f"{clean_name}\n\n#Shorts",
                    "youtube_tags": ["shorts", "viral"],
                }

            # 3. Upload to YouTube
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
                log.info(f"  Uploaded: {url}")
                print(f"\n✓ [{i}/{len(videos)}] {draft.get('youtube_title')}\n  {url}")
            except Exception as e:
                log.warning(f"  YouTube upload failed: {e}")

    return urls
