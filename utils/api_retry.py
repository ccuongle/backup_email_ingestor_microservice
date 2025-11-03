import asyncio
import random
import httpx
from functools import wraps
from logging import getLogger

logger = getLogger(__name__)

def api_retry(max_retries: int, initial_backoff: float, backoff_factor: float):
    """
    A decorator for retrying API calls with exponential backoff and jitter.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            backoff = initial_backoff
            last_exception = None
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    last_exception = e
                    if e.response.status_code in [429, 503]:
                        retry_after = e.response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = int(retry_after)
                            except ValueError:
                                # Handle cases where Retry-After is a date string
                                from datetime import datetime, timezone
                                retry_dt = datetime.strptime(retry_after, "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
                                delay = (retry_dt - datetime.now(timezone.utc)).total_seconds()
                        else:
                            delay = backoff + random.uniform(0, 1)  # Add jitter

                        if delay < 0:
                            delay = 0

                        logger.warning(
                            f"API call to {e.request.url} failed with status {e.response.status_code}. "
                            f"Retrying in {delay:.2f} seconds. (Attempt {retries + 1}/{max_retries})"
                        )
                        await asyncio.sleep(delay)
                        retries += 1
                        backoff *= backoff_factor
                    else:
                        raise
                except httpx.RequestError as e:
                    last_exception = e
                    logger.error(f"Request to {e.request.url} failed: {e}")
                    raise
            logger.error(f"API call failed after {max_retries} retries.")
            if last_exception:
                raise last_exception
            raise RuntimeError("API call failed after max retries.")
        return wrapper
    return decorator
