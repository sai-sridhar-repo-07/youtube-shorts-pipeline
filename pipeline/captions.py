import subprocess
from pathlib import Path

from pipeline.config import VIDEO_WIDTH, VIDEO_HEIGHT
from pipeline.log import get_logger

log = get_logger("captions")

WORDS_PER_GROUP = 4


def _whisper_word_timestamps(audio: Path) -> list:
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(str(audio), word_timestamps=True)
        words = []
        for seg in result.get("segments", []):
            for w in seg.get("words", []):
                words.append({
                    "word": w["word"].strip(),
                    "start": w["start"],
                    "end": w["end"],
                })
        return words
    except ImportError:
        log.warning("whisper not installed, trying CLI fallback")
        return _whisper_cli_fallback(audio)


def _whisper_cli_fallback(audio: Path) -> list:
    import json as _json

    out_dir = audio.parent
    subprocess.run(
        ["whisper", str(audio), "--model", "base", "--output_format", "json",
         "--output_dir", str(out_dir), "--word_timestamps", "True"],
        check=True, capture_output=True
    )
    json_out = out_dir / (audio.stem + ".json")
    with open(json_out) as f:
        data = _json.load(f)

    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            words.append({
                "word": w["word"].strip(),
                "start": w["start"],
                "end": w["end"],
            })
    return words


def _group_words(words: list, n: int = WORDS_PER_GROUP) -> list:
    groups = []
    for i in range(0, len(words), n):
        chunk = words[i:i + n]
        groups.append({
            "words": chunk,
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "text": " ".join(w["word"] for w in chunk),
        })
    return groups


def _format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _generate_ass(words: list, job_dir: Path) -> Path:
    margin_v = int(VIDEO_HEIGHT * 0.08)
    font_size = int(VIDEO_WIDTH * 0.055)
    out = job_dir / "captions.ass"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {VIDEO_WIDTH}
PlayResY: {VIDEO_HEIGHT}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,3,1,2,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    groups = _group_words(words)
    for group in groups:
        group_start = group["start"]
        group_end = group["end"]
        for i, word in enumerate(group["words"]):
            # Build line: current word highlighted yellow, others white
            parts = []
            for j, w in enumerate(group["words"]):
                text = w["word"].replace("{", "\\{")
                if j == i:
                    parts.append(f"{{\\c&H00FFFF&}}{text}{{\\c&H00FFFFFF&}}")
                else:
                    parts.append(text)
            line = " ".join(parts)
            w_start = _format_ass_time(word["start"])
            w_end = _format_ass_time(word["end"])
            events.append(f"Dialogue: 0,{w_start},{w_end},Default,,0,0,0,,{line}")

    with open(out, "w", encoding="utf-8") as f:
        f.write(header)
        f.write("\n".join(events))

    return out


def _generate_srt(words: list, job_dir: Path) -> Path:
    out = job_dir / "captions.srt"
    groups = _group_words(words)
    lines = []
    for i, group in enumerate(groups, 1):
        lines.append(str(i))
        lines.append(f"{_srt_time(group['start'])} --> {_srt_time(group['end'])}")
        lines.append(group["text"])
        lines.append("")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out


def generate_captions(audio: Path, job_dir: Path) -> tuple:
    ass_path = job_dir / "captions.ass"
    srt_path = job_dir / "captions.srt"

    if ass_path.exists() and srt_path.exists():
        log.info("Reusing existing captions")
        return ass_path, srt_path

    log.info("Transcribing audio with Whisper...")
    words = _whisper_word_timestamps(audio)

    if not words:
        log.warning("No words from Whisper, captions will be empty")
        ass_path.write_text("")
        srt_path.write_text("")
        return ass_path, srt_path

    log.info(f"Transcribed {len(words)} words, generating captions...")
    ass = _generate_ass(words, job_dir)
    srt = _generate_srt(words, job_dir)
    return ass, srt
