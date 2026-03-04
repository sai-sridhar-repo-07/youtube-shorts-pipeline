import requests
from pipeline.config import load_config
from pipeline.log import get_logger

log = get_logger("topics.reddit")

DEFAULT_SUBREDDITS = ["technology", "worldnews", "science", "todayilearned"]
HEADERS = {"User-Agent": "shorts-pipeline/1.0 (automated video creation)"}


def get_reddit_topics(subreddits: list = None, limit: int = 10) -> list:
    cfg = load_config()
    src_cfg = cfg.get("topic_sources", {}).get("reddit", {})
    if not src_cfg.get("enabled", True):
        return []

    subs = subreddits or src_cfg.get("subreddits", DEFAULT_SUBREDDITS)
    topics = []

    for sub in subs:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=5"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            posts = resp.json()["data"]["children"]
            for post in posts:
                title = post["data"].get("title", "").strip()
                if title and len(title) > 10:
                    topics.append(title)
        except Exception as e:
            log.warning(f"Reddit r/{sub} failed: {e}")

    log.info(f"Got {len(topics)} topics from Reddit")
    return topics[:limit]
