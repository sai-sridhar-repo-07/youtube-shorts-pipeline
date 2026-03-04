"""
RSS-based topic discovery — works from any IP including GitHub Actions.
Uses free public RSS feeds (BBC, Reuters, AP, NPR, etc.) with no auth required.
"""
import re
import xml.etree.ElementTree as ET

import requests

from pipeline.log import get_logger

log = get_logger("topics.rss")

# Public RSS feeds that work from datacenter IPs (no bot blocking)
RSS_FEEDS = [
    "https://feeds.bbci.co.uk/news/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
    "https://feeds.bbci.co.uk/news/health/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
    "https://feeds.feedburner.com/TechCrunch",
    "https://www.theguardian.com/science/rss",
    "https://www.theguardian.com/technology/rss",
    "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "https://www.sciencedaily.com/rss/top/science.xml",
    "https://www.livescience.com/feeds/all",
    "https://www.space.com/feeds/all",
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://www.wired.com/feed/rss",
    "https://www.psychologytoday.com/intl/front-page/feed",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; RSS reader; +https://github.com/shorts-pipeline)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# Words that make a headline bad for a YouTube Short topic
_SKIP_WORDS = [
    "obituary", "kills", "dead", "shooting", "murder", "dies", "death",
    "arrested", "charged", "indicted", "lawsuit", "impeach", "resign",
    "election", "vote", "ballot", "trump", "biden", "congress", "senate",
    "war", "attack", "bomb", "terror", "crash", "accident", "fire",
    "recall", "scandal", "fraud", "leak", "hack", "breach",
]


def _clean_title(title: str) -> str:
    """Strip HTML entities and extra whitespace."""
    title = re.sub(r"<[^>]+>", "", title)
    title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    title = title.replace("&#39;", "'").replace("&quot;", '"')
    return title.strip()


def _is_good_topic(title: str) -> bool:
    low = title.lower()
    if len(title) < 15 or len(title) > 120:
        return False
    if any(w in low for w in _SKIP_WORDS):
        return False
    # Skip if it looks like a question that's too vague
    if title.endswith("?") and len(title) < 25:
        return False
    return True


def _reframe_as_short(title: str) -> str:
    """Optionally reframe plain news headline into a Short-friendly phrasing."""
    # If it already starts with "How", "Why", "The", "What", keep as-is
    if title[:3] in ("How", "Why", "The", "Wha", "Thi", "Whe"):
        return title
    # Prefix with "The science behind:" for science/tech topics
    low = title.lower()
    if any(w in low for w in ["discover", "study", "research", "found", "reveal", "scientists"]):
        return f"Scientists just discovered: {title}"
    return title


def get_rss_topics(limit: int = 15) -> list:
    """Fetch topic headlines from public RSS feeds. Works from any IP."""
    topics = []

    for feed_url in RSS_FEEDS:
        if len(topics) >= limit * 3:
            break
        try:
            resp = requests.get(feed_url, headers=HEADERS, timeout=8)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            # Handle both RSS 2.0 and Atom
            items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
            for item in items[:8]:
                title_el = item.find("title") or item.find("{http://www.w3.org/2005/Atom}title")
                if title_el is None or not title_el.text:
                    continue
                title = _clean_title(title_el.text)
                if _is_good_topic(title):
                    topics.append(_reframe_as_short(title))

        except Exception as e:
            log.debug(f"RSS feed failed ({feed_url}): {e}")

    log.info(f"Got {len(topics)} topics from RSS feeds")
    return topics[:limit]
