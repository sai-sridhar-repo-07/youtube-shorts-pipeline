import random
import subprocess
from pathlib import Path

from pipeline.config import MUSIC_DIR
from pipeline.log import get_logger

log = get_logger("music")


def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def pick_music() -> Path | None:
    if not MUSIC_DIR.exists():
        log.warning(f"Music directory not found: {MUSIC_DIR}")
        return None

    tracks = list(MUSIC_DIR.glob("*.mp3")) + list(MUSIC_DIR.glob("*.m4a"))
    if not tracks:
        log.warning("No music tracks found in music/ directory")
        return None

    track = random.choice(tracks)
    log.info(f"Selected music: {track.name}")
    return track
