import subprocess
from pathlib import Path

from pipeline.broll import animate_frame, EFFECTS, TRANSITIONS
from pipeline.music import get_audio_duration
from pipeline.config import VIDEO_WIDTH, VIDEO_HEIGHT, FPS
from pipeline.log import get_logger

log = get_logger("assemble")


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

def _srt_time_to_seconds(s: str) -> float:
    s = s.strip()
    h, m, rest = s.split(":")
    sec, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000


def _parse_srt(srt_path: Path) -> list:
    """Return list of (start_sec, end_sec, text) from an SRT file."""
    entries = []
    text = srt_path.read_text(encoding="utf-8")
    for block in text.strip().split("\n\n"):
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        for i, line in enumerate(lines):
            if " --> " in line:
                parts = line.split(" --> ")
                start = _srt_time_to_seconds(parts[0])
                end = _srt_time_to_seconds(parts[1])
                caption = " ".join(lines[i + 1:])
                if caption:
                    entries.append((start, end, caption))
                break
    return entries


# ---------------------------------------------------------------------------
# PIL caption burn (no libass / drawtext needed)
# ---------------------------------------------------------------------------

def _burn_captions_pil(video_in: Path, srt_path: Path, video_out: Path) -> None:
    """Pipe video frames through PIL, stamp caption text, re-encode."""
    from PIL import Image, ImageDraw, ImageFont

    entries = _parse_srt(srt_path)
    if not entries:
        log.warning("No caption entries in SRT — skipping caption burn")
        import shutil
        shutil.copy2(str(video_in), str(video_out))
        return

    log.info(f"Burning {len(entries)} caption entries via PIL…")

    w, h = VIDEO_WIDTH, VIDEO_HEIGHT
    fps = FPS
    bytes_per_frame = w * h * 3
    font_size = int(w * 0.10)  # 10% of width = ~108px on 1080p — big and readable

    # Font search order: macOS paths first, then Linux/Ubuntu (GitHub Actions)
    font = None
    for fp in [
        # macOS
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        # Ubuntu / Debian (GitHub Actions)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        # Fallback any bold sans
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ]:
        try:
            font = ImageFont.truetype(fp, font_size)
            log.info(f"Caption font: {fp} @ {font_size}px")
            break
        except Exception:
            pass
    if font is None:
        # Last resort — install a font via apt in the workflow, but don't crash
        log.warning("No truetype font found — captions will be tiny. Add fonts-dejavu to your workflow.")
        try:
            font = ImageFont.load_default(size=font_size)
        except TypeError:
            font = ImageFont.load_default()

    cmd_decode = [
        "ffmpeg", "-i", str(video_in),
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-vsync", "cfr",
        "pipe:1",
    ]
    cmd_encode = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}",
        "-r", str(fps),
        "-i", "pipe:0",
        "-i", str(video_in),          # source for audio copy
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(video_out),
    ]

    proc_dec = subprocess.Popen(cmd_decode, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    proc_enc = subprocess.Popen(cmd_encode, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    frame_num = 0
    try:
        while True:
            raw = proc_dec.stdout.read(bytes_per_frame)
            if len(raw) < bytes_per_frame:
                break

            t = frame_num / fps
            caption_text = next((txt for s, e, txt in entries if s <= t < e), None)

            img = Image.frombytes("RGB", (w, h), raw)

            if caption_text:
                draw = ImageDraw.Draw(img)

                # Word-wrap caption to fit within 90% of frame width
                max_w = int(w * 0.90)
                words = caption_text.split()
                lines, line = [], []
                for word in words:
                    test = " ".join(line + [word])
                    try:
                        tw = draw.textbbox((0, 0), test, font=font)[2]
                    except AttributeError:
                        tw, _ = draw.textsize(test, font=font)
                    if tw <= max_w:
                        line.append(word)
                    else:
                        if line:
                            lines.append(" ".join(line))
                        line = [word]
                if line:
                    lines.append(" ".join(line))

                # Measure total block height
                line_height = font_size + int(font_size * 0.2)
                block_h = line_height * len(lines)

                # Position: bottom 15% of frame
                block_y = h - int(h * 0.15) - block_h

                outline = max(4, font_size // 14)
                offsets = [
                    (-outline, -outline), (0, -outline), (outline, -outline),
                    (-outline, 0),                        (outline, 0),
                    (-outline,  outline), (0,  outline), (outline,  outline),
                ]
                for li, text_line in enumerate(lines):
                    try:
                        lw = draw.textbbox((0, 0), text_line, font=font)[2]
                    except AttributeError:
                        lw, _ = draw.textsize(text_line, font=font)
                    x = (w - lw) // 2
                    y = block_y + li * line_height
                    for dx, dy in offsets:
                        draw.text((x + dx, y + dy), text_line, font=font, fill=(0, 0, 0))
                    draw.text((x, y), text_line, font=font, fill=(255, 255, 255))

            proc_enc.stdin.write(img.tobytes())
            frame_num += 1

    finally:
        proc_dec.stdout.close()
        proc_dec.wait()
        proc_enc.stdin.close()
        proc_enc.wait()

    if proc_enc.returncode != 0:
        raise RuntimeError("PIL caption re-encode failed")

    log.info(f"Caption burn complete ({frame_num} frames)")


# ---------------------------------------------------------------------------
# Audio assembly helpers
# ---------------------------------------------------------------------------

def _assemble_voice_only(video: Path, voiceover: Path, out: Path, duration: float) -> None:
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(voiceover),
            "-map", "0:v",
            "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(duration),
            str(out),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg voice-only assembly failed:\n{result.stderr[-500:]}")


def _assemble_with_music(
    video: Path, voiceover: Path, music: Path, out: Path, duration: float
) -> None:
    music_filter = (
        f"[1:a]atrim=0:{duration},aloop=loop=-1:size=44100*{int(duration)+1},"
        f"atrim=0:{duration}[music_trim];"
        "[2:a]aformat=fltp[voice];"
        "[music_trim][voice]sidechaincompress=threshold=0.02:ratio=4:attack=5:release=200[music_duck];"
        "[music_duck][voice]amix=inputs=2:duration=first:weights=0.3 1[audio_out]"
    )
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video),
            "-i", str(music),
            "-i", str(voiceover),
            "-filter_complex", music_filter,
            "-map", "0:v",
            "-map", "[audio_out]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-t", str(duration),
            str(out),
        ],
        capture_output=True,
    )
    if result.returncode != 0:
        log.warning(f"Music assembly failed, falling back to voice-only: {result.stderr[-300:]}")
        _assemble_voice_only(video, voiceover, out, duration)


# ---------------------------------------------------------------------------
# Clip joining with xfade transitions
# ---------------------------------------------------------------------------

def _concat_with_transitions(
    clips: list, clip_duration: float, out: Path, job_dir: Path,
    transition_duration: float = 0.5,
) -> None:
    """Join clips with smooth xfade transitions between each pair."""
    if len(clips) == 1:
        import shutil
        shutil.copy2(str(clips[0]), str(out))
        return

    # Build ffmpeg filter_complex chaining xfade for N clips
    # offset_i = (i+1) * (clip_duration - transition_duration)
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]

    filter_parts = []
    td = transition_duration
    n = len(clips)

    for i in range(n - 1):
        transition = TRANSITIONS[i % len(TRANSITIONS)]
        offset = round((i + 1) * (clip_duration - td), 4)
        in_a = f"[v{i}]" if i > 0 else "[0:v]"
        in_b = f"[{i+1}:v]"
        out_label = f"[v{i+1}]"
        filter_parts.append(
            f"{in_a}{in_b}xfade=transition={transition}"
            f":duration={td}:offset={offset}{out_label}"
        )

    filter_complex = ";".join(filter_parts)
    final_label = f"[v{n-1}]"

    cmd = (
        ["ffmpeg", "-y"]
        + inputs
        + [
            "-filter_complex", filter_complex,
            "-map", final_label,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
            str(out),
        ]
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.warning(f"xfade transitions failed — falling back to plain concat: {result.stderr[-300:]}")
        _plain_concat(clips, out)


def _plain_concat(clips: list, out: Path) -> None:
    """Fallback: plain cut concat with no transitions."""
    import tempfile, os
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for c in clips:
            f.write(f"file '{c.resolve()}'\n")
        tmp = f.name
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", tmp, "-c", "copy", str(out)],
        capture_output=True, check=True,
    )
    os.unlink(tmp)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def assemble_video(
    frames: list,
    voiceover: Path,
    music: Path | None,
    captions_ass: Path | None,
    job_dir: Path,
    job_id: str,
) -> Path:
    duration = get_audio_duration(voiceover)
    if duration <= 0:
        raise ValueError(f"Could not get duration of voiceover: {voiceover}")

    frame_duration = duration / len(frames)
    log.info(f"Total duration: {duration:.1f}s, {frame_duration:.1f}s per frame")

    # Animate each frame — pick a unique effect per clip
    clips = []
    for i, frame in enumerate(frames):
        effect = EFFECTS[i % len(EFFECTS)]
        clip_out = job_dir / f"clip_{i}.mp4"
        if not clip_out.exists():
            log.info(f"Animating frame {i+1}/{len(frames)} — effect: {effect}")
            animate_frame(frame, frame_duration, effect, clip_out)
        clips.append(clip_out)

    # Join clips → video_raw.mp4 (plain cut, no transitions)
    concat_out = job_dir / "video_raw.mp4"
    if not concat_out.exists():
        _plain_concat(clips, concat_out)

    # Assemble with audio
    final_out = job_dir / f"final_{job_id}.mp4"
    log.info("Assembling final video with audio…")

    if music and music.exists():
        _assemble_with_music(concat_out, voiceover, music, final_out, duration)
    else:
        _assemble_voice_only(concat_out, voiceover, final_out, duration)

    # Burn captions via PIL (no libass needed)
    srt_path = captions_ass.with_suffix(".srt") if captions_ass else None
    if srt_path and srt_path.exists() and srt_path.stat().st_size > 0:
        captioned_out = job_dir / f"final_{job_id}_cap.mp4"
        try:
            _burn_captions_pil(final_out, srt_path, captioned_out)
            final_out.unlink()
            captioned_out.rename(final_out)
        except Exception as e:
            log.warning(f"Caption burn failed: {e} — video saved without burnt-in captions")
            if captioned_out.exists():
                captioned_out.unlink()

    log.info(f"Final video: {final_out}")
    return final_out
