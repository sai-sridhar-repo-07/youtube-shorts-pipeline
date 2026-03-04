from pipeline.log import get_logger
from pipeline.retry import with_retry

log = get_logger("research")

MAX_CHARS = 3000


@with_retry(max_retries=2, delay=3)
def research_topic(topic: str) -> str:
    try:
        from ddgs import DDGS
    except ImportError:
        log.warning("ddgs not installed, skipping research")
        return f"Topic: {topic}"

    log.info(f"Researching: {topic}")
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(topic, max_results=6):
            snippet = r.get("body", "").strip()
            if snippet:
                results.append(f"- {snippet}")

    combined = "\n".join(results)
    if len(combined) > MAX_CHARS:
        combined = combined[:MAX_CHARS]

    log.info(f"Research complete: {len(combined)} chars")
    return combined or f"Topic: {topic}"
