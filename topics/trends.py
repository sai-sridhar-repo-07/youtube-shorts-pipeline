from pipeline.config import load_config
from pipeline.log import get_logger

log = get_logger("topics.trends")


def get_google_trends(geo: str = None, limit: int = 10) -> list:
    cfg = load_config()
    src_cfg = cfg.get("topic_sources", {}).get("google_trends", {})
    if not src_cfg.get("enabled", True):
        return []

    region = geo or src_cfg.get("geo", "US")

    try:
        from pytrends.request import TrendReq

        pytrends = TrendReq(hl="en-US", tz=360, timeout=(5, 30))
        df = pytrends.trending_searches(pn=region.lower())
        topics = df[0].tolist()
        log.info(f"Got {len(topics)} topics from Google Trends ({region})")
        return topics[:limit]
    except ImportError:
        log.warning("pytrends not installed")
        return []
    except Exception as e:
        log.warning(f"Google Trends failed: {e}")
        return []
