import time
import functools
from pipeline.log import get_logger

log = get_logger("retry")


def with_retry(max_retries: int = 3, delay: float = 2.0, backoff: float = 2.0):
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(1, max_retries + 2):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    if attempt > max_retries:
                        log.error(f"{fn.__name__} failed after {max_retries} retries: {e}")
                        raise
                    log.warning(f"{fn.__name__} attempt {attempt} failed: {e}. Retrying in {current_delay:.1f}s...")
                    time.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator
