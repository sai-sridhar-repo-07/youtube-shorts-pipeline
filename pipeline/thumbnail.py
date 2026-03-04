from pathlib import Path

from pipeline.config import load_config
from pipeline.log import get_logger
from pipeline.retry import with_retry

log = get_logger("thumbnail")

THUMB_W = 1280
THUMB_H = 720

_HF_MODELS = [
    "stabilityai/stable-diffusion-xl-base-1.0",
    "runwayml/stable-diffusion-v1-5",
    "CompVis/stable-diffusion-v1-4",
]


def _hf_image(prompt: str, out: Path, hf_token: str) -> None:
    from huggingface_hub import InferenceClient

    client = InferenceClient(token=hf_token)
    last_err = None
    for model in _HF_MODELS:
        try:
            image = client.text_to_image(prompt[:300], model=model)
            image.save(str(out), "PNG")
            return
        except Exception as e:
            log.warning(f"Thumbnail model {model} failed: {e}")
            last_err = e
    raise ValueError(f"All HF thumbnail models failed: {last_err}")


def _draw_title(img_path: Path, title: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.open(img_path).convert("RGB").resize((THUMB_W, THUMB_H))
    draw = ImageDraw.Draw(img)

    # Simple text with shadow — no custom font required
    font_size = 72
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except Exception:
        font = ImageFont.load_default()

    max_chars = 30
    display = title[:max_chars] + ("..." if len(title) > max_chars else "")

    bbox = draw.textbbox((0, 0), display, font=font)
    tw = bbox[2] - bbox[0]
    x = (THUMB_W - tw) // 2
    y = THUMB_H - 180

    # Shadow
    draw.text((x + 3, y + 3), display, font=font, fill=(0, 0, 0, 180))
    # Main text
    draw.text((x, y), display, font=font, fill=(255, 255, 255))

    img.save(img_path, "PNG")


def generate_thumbnail(prompt: str, title: str, job_dir: Path) -> Path:
    out = job_dir / "thumbnail.png"
    if out.exists():
        log.info("Reusing existing thumbnail")
        return out

    cfg = load_config()
    hf_token = cfg.get("HF_TOKEN", "")
    try:
        log.info("Generating thumbnail with Hugging Face FLUX...")
        _hf_image(f"YouTube thumbnail, cinematic, photorealistic: {prompt[:200]}", out, hf_token)
    except Exception as e:
        log.warning(f"Thumbnail generation failed: {e}, using fallback")
        _fallback_thumbnail(out, title)

    _draw_title(out, title)
    log.info(f"Thumbnail saved: {out.name}")
    return out


def _fallback_thumbnail(out: Path, title: str) -> None:
    from PIL import Image

    img = Image.new("RGB", (THUMB_W, THUMB_H), (20, 20, 50))
    img.save(out, "PNG")
