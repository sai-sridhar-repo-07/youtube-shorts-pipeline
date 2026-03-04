import subprocess
from pathlib import Path

from pipeline.config import load_config
from pipeline.log import get_logger
from pipeline.retry import with_retry

log = get_logger("voiceover")


@with_retry(max_retries=3, delay=2)
def _call_elevenlabs(script: str, out_path: Path, api_key: str, voice_id: str) -> None:
    import requests

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": script,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 0.85,
            "style": 0.3,
            "use_speaker_boost": True,
        },
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
    log.info(f"ElevenLabs voiceover saved: {out_path.name}")


def _macos_say_fallback(script: str, out_path: Path) -> None:
    log.warning("Falling back to macOS 'say' command")
    aiff = out_path.with_suffix(".aiff")
    subprocess.run(["say", "-o", str(aiff), script], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), str(out_path)],
        capture_output=True, check=True
    )
    aiff.unlink(missing_ok=True)
    log.info(f"macOS say fallback saved: {out_path.name}")


def generate_voiceover(script: str, job_dir: Path, lang: str = "en") -> Path:
    cfg = load_config()
    api_key = cfg.get("ELEVENLABS_API_KEY", "")
    voice_id = cfg.get("VOICE_ID_EN", "21m00Tcm4TlvDq8ikWAM")

    out_path = job_dir / f"voiceover_{lang}.mp3"
    if out_path.exists():
        log.info("Reusing existing voiceover")
        return out_path

    if api_key and voice_id:
        try:
            _call_elevenlabs(script, out_path, api_key, voice_id)
            return out_path
        except Exception as e:
            log.warning(f"ElevenLabs failed: {e}")

    _macos_say_fallback(script, out_path)
    return out_path
