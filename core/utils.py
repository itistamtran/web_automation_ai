import time
from typing import Callable

def retry(fn: Callable, tries: int = 3, delay: float = 1.0):
    """
    Run a callable with simple retries.
    """
    last_err = None
    for _ in range(tries):
        try:
            return fn()
        except Exception as e:
            last_err = e
            time.sleep(delay)
    if last_err:
        raise last_err
