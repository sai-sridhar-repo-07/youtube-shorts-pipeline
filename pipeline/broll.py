import subprocess
from pathlib import Path

from pipeline.config import load_config, VIDEO_WIDTH, VIDEO_HEIGHT, FPS
from pipeline.log import get_logger
from pipeline.retry import with_retry

log = get_logger("broll")

EFFECTS = ["zoom_in", "pan_right", "zoom_out", "pan_left", "pan_up", "pan_down"]

# Models tried in order — first one that works is used
_HF_MODELS = [
    "stabilityai/stable-diffusion-xl-base-1.0",
    "runwayml/stable-diffusion-v1-5",
    "CompVis/stable-diffusion-v1-4",
]


def _generate_image_pexels(prompt: str, out_path: Path, api_key: str) -> bool:
    """Fetch a relevant stock photo from Pexels (free, no credits needed)."""
    import requests
    from PIL import Image
    import io

    # Use first few words as search query
    query = " ".join(prompt.split()[:6])
    headers = {"Authorization": api_key}
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers=headers,
        params={"query": query, "per_page": 5, "orientation": "portrait"},
        timeout=15,
    )
    resp.raise_for_status()
    photos = resp.json().get("photos", [])
    if not photos:
        # Retry with shorter query
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params={"query": query.split()[0], "per_page": 5, "orientation": "portrait"},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
    if not photos:
        raise ValueError(f"No Pexels results for: {query}")

    photo_url = photos[0]["src"]["large2x"]
    img_resp = requests.get(photo_url, timeout=30)
    img_resp.raise_for_status()
    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
    img.save(str(out_path), "PNG")
    log.info(f"Saved Pexels image: {out_path.name} (query: {query})")
    return True


def _generate_image_hf(prompt: str, out_path: Path, hf_token: str) -> bool:
    """Image generation via HF InferenceClient (SDXL, free tier)."""
    from huggingface_hub import InferenceClient

    client = InferenceClient(token=hf_token)
    last_err = None
    for model in _HF_MODELS:
        try:
            log.info(f"Trying model: {model}")
            image = client.text_to_image(prompt[:300], model=model)
            image.save(str(out_path), "PNG")
            log.info(f"Saved image: {out_path.name} via {model}")
            return True
        except Exception as e:
            log.warning(f"Model {model} failed: {e}")
            last_err = e
    raise ValueError(f"All HF models failed. Last error: {last_err}")


def _fallback_frame(out_path: Path, index: int) -> None:
    from PIL import Image

    colors = [(20, 20, 40), (10, 30, 20), (30, 10, 10)]
    color = colors[index % len(colors)]
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), color)
    img.save(out_path, "PNG")
    log.warning(f"Used fallback placeholder for frame {index}")


def _resize_to_portrait(img_path: Path) -> None:
    from PIL import Image

    img = Image.open(img_path).convert("RGB")
    target_ratio = VIDEO_WIDTH / VIDEO_HEIGHT

    w, h = img.size
    current_ratio = w / h

    if current_ratio > target_ratio:
        # Too wide — crop width
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        # Too tall — crop height
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
    img.save(img_path, "PNG")


def generate_broll(prompts: list, job_dir: Path) -> list:
    cfg = load_config()
    api_key = cfg.get("GEMINI_API_KEY", "")
    frames = []

    for i, prompt in enumerate(prompts[:6]):
        out = job_dir / f"frame_{i}.png"
        if out.exists():
            log.info(f"Reusing existing frame {i}")
            frames.append(out)
            continue

        log.info(f"Generating image {i+1}/{len(prompts[:6])}: {prompt[:60]}...")
        generated = False

        # 1. Try Pexels (free stock photos, no credits)
        pexels_key = cfg.get("PEXELS_API_KEY", "")
        if pexels_key and not generated:
            try:
                _generate_image_pexels(prompt, out, pexels_key)
                generated = True
            except Exception as e:
                log.warning(f"Pexels failed for frame {i}: {e}")

        # 2. Try HuggingFace AI generation
        hf_token = cfg.get("HF_TOKEN", "")
        if hf_token and not generated:
            try:
                _generate_image_hf(prompt, out, hf_token)
                generated = True
            except Exception as e:
                log.warning(f"HF failed for frame {i}: {e}")

        if not generated:
            log.warning(f"All image sources failed for frame {i}, using placeholder")
            _fallback_frame(out, i)

        _resize_to_portrait(out)
        frames.append(out)

    return frames


def animate_frame(img: Path, duration: float, effect: str, out: Path) -> Path:
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT
    fps = FPS
    n_frames = int(duration * fps)

    if effect == "zoom_in":
        zoom_expr = f"1.0+0.3*on/{n_frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif effect == "zoom_out":
        zoom_expr = f"1.3-0.3*on/{n_frames}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif effect == "pan_right":
        zoom_expr = "1.2"
        x_expr = f"(iw-iw/zoom)/2*on/{n_frames}"
        y_expr = "ih/2-(ih/zoom/2)"
    elif effect == "pan_left":
        zoom_expr = "1.2"
        x_expr = f"(iw-iw/zoom)/2*(1-on/{n_frames})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif effect == "pan_up":
        zoom_expr = "1.2"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)/2*(1-on/{n_frames})"
    else:  # pan_down
        zoom_expr = "1.2"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)/2*on/{n_frames}"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(img),
        "-vf", (
            f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}'"
            f":d={n_frames}:s={w}x{h}:fps={fps}"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f"FFmpeg animate_frame failed: {result.stderr[-500:]}")
        raise RuntimeError("FFmpeg animate_frame failed")
    return out
