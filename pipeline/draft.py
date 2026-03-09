import json
import re
from pipeline.log import get_logger
from pipeline.retry import with_retry
from pipeline.config import load_config

log = get_logger("draft")

_SYSTEM = """You are a YouTube Shorts scriptwriter. Output ONLY valid JSON — no markdown fences, no explanation, no refusals, no extra text. Just the raw JSON object."""

_PROMPT = """
Topic: {topic}

<research>
{research}
</research>

{channel_context}

Write an engaging YouTube Short script about the topic above.
Use the research if it is helpful. If the research is thin or irrelevant, use your own knowledge — do NOT refuse, do NOT explain, just write the script.

Return ONLY a single JSON object with these exact keys:
{{
  "script": "conversational voiceover, 150-180 words, punchy and engaging, starts with a hook",
  "broll_prompts": ["cinematic visual prompt 1", "cinematic visual prompt 2", "cinematic visual prompt 3", "cinematic visual prompt 4", "cinematic visual prompt 5", "cinematic visual prompt 6"],
  "youtube_title": "catchy title under 70 chars with relevant emoji",
  "youtube_description": "2-3 sentence description with hashtags",
  "youtube_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "thumbnail_prompt": "detailed visual prompt for a 16:9 thumbnail image"
}}
"""

_FALLBACK_BROLL = [
    "Cinematic aerial shot of a futuristic city at sunset, golden hour lighting",
    "Close-up of glowing technology interface with blue light effects",
    "Wide establishing shot of modern skyline with dramatic clouds",
    "Dramatic low-angle shot of skyscrapers reaching into cloudy sky",
    "Slow motion close-up of data streams flowing through fiber optic cables",
    "Time-lapse of city traffic at night with light trails on wet road",
]


@with_retry(max_retries=2, delay=5)
def generate_draft(topic: str, research: str, channel_context: str = "") -> dict:
    cfg = load_config()
    api_key = cfg.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured. Run: python -m pipeline setup")

    import anthropic

    log.info("Generating script with Claude...")
    context_block = f"Channel context: {channel_context}\n" if channel_context else ""
    prompt = _PROMPT.format(topic=topic, research=research, channel_context=context_block)

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = msg.content[0].text.strip()

    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        draft = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"Claude returned invalid JSON: {e}\nRaw: {raw[:300]}")
        raise ValueError(f"Claude returned invalid JSON: {e}")

    # Validate and sanitize
    if not isinstance(draft.get("script"), str):
        raise ValueError("draft.script missing or not a string")
    if not isinstance(draft.get("broll_prompts"), list) or len(draft["broll_prompts"]) < 6:
        log.warning("broll_prompts invalid or too few, using fallback")
        draft["broll_prompts"] = _FALLBACK_BROLL
    else:
        draft["broll_prompts"] = [
            p if isinstance(p, str) else _FALLBACK_BROLL[i]
            for i, p in enumerate(draft["broll_prompts"][:6])
        ]
    if not isinstance(draft.get("youtube_title"), str):
        draft["youtube_title"] = topic[:70]
    if not isinstance(draft.get("youtube_description"), str):
        draft["youtube_description"] = topic
    if not isinstance(draft.get("youtube_tags"), list):
        draft["youtube_tags"] = [topic]
    if not isinstance(draft.get("thumbnail_prompt"), str):
        draft["thumbnail_prompt"] = f"Cinematic scene related to {topic}"

    draft["topic"] = topic
    draft["research"] = research

    log.info(f"Draft ready: '{draft['youtube_title']}'")
    return draft
