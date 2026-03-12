import json
import os
import stat
from pathlib import Path

CONFIG_DIR = Path.home() / ".shorts-pipeline"
CONFIG_FILE = CONFIG_DIR / "config.json"
JOBS_DIR = CONFIG_DIR / "jobs"
LOGS_DIR = CONFIG_DIR / "logs"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

MUSIC_DIR = Path(__file__).parent.parent / "music"

_DEFAULTS = {
    "ANTHROPIC_API_KEY": "",
    "GEMINI_API_KEY": "",
    "ELEVENLABS_API_KEY": "",
    "VOICE_ID_EN": "21m00Tcm4TlvDq8ikWAM",
    "HF_TOKEN": "",
    "PEXELS_API_KEY": "",
    "INSTAGRAM_ACCESS_TOKEN": "",
    "INSTAGRAM_USER_ID": "",
    "channel_context": "",
    "topic_sources": {
        "reddit": {"enabled": True, "subreddits": ["technology", "worldnews", "science"]},
        "google_trends": {"enabled": True, "geo": "US"},
    },
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_FILE.exists():
        save_config(_DEFAULTS.copy())
        return _DEFAULTS.copy()

    with open(CONFIG_FILE) as f:
        cfg = json.load(f)

    # Fill in any missing keys from defaults
    for k, v in _DEFAULTS.items():
        if k not in cfg:
            cfg[k] = v

    # Environment variables override config
    for key in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY", "VOICE_ID_EN", "HF_TOKEN",
                "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID"):
        env_val = os.environ.get(key)
        if env_val:
            cfg[key] = env_val

    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
    tmp.rename(CONFIG_FILE)


def setup_wizard() -> dict:
    print("\n=== YouTube Shorts Pipeline Setup ===\n")
    cfg = load_config()

    prompts = [
        ("ANTHROPIC_API_KEY", "Anthropic API key (for script generation)"),
        ("PEXELS_API_KEY", "Pexels API key (FREE photos — get at pexels.com/api, press Enter to skip)"),
        ("HF_TOKEN", "Hugging Face token (AI image generation — free at huggingface.co/settings/tokens)"),
        ("ELEVENLABS_API_KEY", "ElevenLabs API key (for voiceover, optional — press Enter to skip)"),
        ("VOICE_ID_EN", "ElevenLabs Voice ID for English (press Enter for default)"),
        ("channel_context", "Channel context/niche (e.g. 'tech news for beginners', optional)"),
        ("INSTAGRAM_ACCESS_TOKEN", "Instagram long-lived access token (optional — press Enter to skip)"),
        ("INSTAGRAM_USER_ID", "Instagram User ID (numeric, optional — press Enter to skip)"),
    ]

    for key, label in prompts:
        current = cfg.get(key, "")
        display = f"[{current[:8]}...]" if current and len(current) > 8 else f"[{current}]" if current else "[not set]"
        val = input(f"{label} {display}: ").strip()
        if val:
            cfg[key] = val

    save_config(cfg)
    print(f"\nConfig saved to {CONFIG_FILE}")
    print("Next: run `python scripts/setup_youtube_oauth.py` to set up YouTube OAuth.\n")
    return cfg
