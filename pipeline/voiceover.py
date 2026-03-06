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
    """macOS only — uses the built-in 'say' command."""
    aiff = out_path.with_suffix(".aiff")
    subprocess.run(["say", "-o", str(aiff), script], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), str(out_path)],
        capture_output=True, check=True
    )
    aiff.unlink(missing_ok=True)
    log.info(f"macOS say fallback saved: {out_path.name}")


def _edge_tts_fallback(script: str, out_path: Path) -> None:
    """Free Microsoft Edge neural TTS — works on any OS, no API key needed."""
    import asyncio
    import edge_tts

    voice = "en-US-AndrewMultilingualNeural"  # natural male voice

    async def _run():
        communicate = edge_tts.Communicate(script, voice)
        await communicate.save(str(out_path))

    asyncio.run(_run())
    log.info(f"edge-tts voiceover saved: {out_path.name}")


def _tts_fallback(script: str, out_path: Path) -> None:
    """Try edge-tts first (free, neural quality), then OS fallback."""
    try:
        log.warning("ElevenLabs unavailable — falling back to edge-tts (free Microsoft neural voice)")
        _edge_tts_fallback(script, out_path)
        return
    except Exception as e:
        log.warning(f"edge-tts failed: {e}")

    import platform
    if platform.system() == "Darwin":
        log.warning("Falling back to macOS say")
        _macos_say_fallback(script, out_path)
    else:
        log.warning("Falling back to espeak-ng")
        subprocess.run(
            ["espeak-ng", "-s", "145", "-p", "50", "-a", "180",
             "-w", str(out_path.with_suffix(".wav")), script],
            check=True
        )
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(out_path.with_suffix(".wav")), str(out_path)],
            capture_output=True, check=True
        )
        out_path.with_suffix(".wav").unlink(missing_ok=True)


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

    _tts_fallback(script, out_path)
    return out_path
