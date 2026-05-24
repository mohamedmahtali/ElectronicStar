import logging
import time
from functools import wraps
from typing import Callable, Type

logger = logging.getLogger(__name__)


def with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
) -> Callable:
    """Décorateur retry avec backoff exponentiel pour les fonctions sync."""

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    if attempt == max_retries:
                        raise
                    logger.warning("Retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, exc)
                    time.sleep(delay)
                    delay *= 2

        return wrapper

    return decorator
