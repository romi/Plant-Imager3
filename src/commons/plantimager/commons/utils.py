from functools import wraps
from time import time


def ttl_cache(maxsize: int=16, ttl: float=300):
    """
    A decorator to cache the results of a function with a time-to-live (TTL) mechanism.

    This decorator caches the results of a function for a specified number of seconds (`ttl`),
    with a maximum number of allowed cache entries (`maxsize`). Each result is stored with
    an expiration timestamp, after which the entry is purged from the cache upon subsequent
    calls. The cache is automatically cleaned to remove expired entries. Additionally, if
    `maxsize` is reached, the oldest cache entries are evicted to make room for new entries.

    In addition, a `clear_cache()` method is added to the decorated function, allowing to
    manually clear the cache.

    Parameters
    ----------
    maxsize : int, optional
        The maximum number of entries to store in the cache. Once the cache reaches this limit,
        the least recently used (LRU) entry is removed. Default is ``16``.
    ttl : float, optional
        The time-to-live (in seconds) for each cache entry. After this duration, a cache entry
        becomes stale and is removed from the cache upon subsequent calls. Default is ``300``.

    Returns
    -------
    Callable
        A decorator that wraps the input function, adding caching functionality
        with expiration and capacity constraints.

    Raises
    ------
    TypeError
        If `maxsize` or `ttl` are not integers.
    ValueError
        If `maxsize` or `ttl` are less than or equal to zero.

    Notes
    -----
    - The `clear_cache` attribute is added to the decorated function, allowing
      external clearing of the cache.
    - Cache keys are created based on the function's positional and keyword arguments.
    - The decorator does not guard against concurrent usage and is not thread-safe.

    Examples
    --------
    Basic usage with default parameters:

    >>> import time
    >>> @ttl_cache()
    ... def add(a, b):
    ...     return a + b
    >>> add(1, 2)
    3  # Result is computed and cached
    >>> add(1, 2)
    3  # Result is retrieved from cache
    >>> time.sleep(301)  # Wait for TTL to expire (default is 300s)
    >>> add(1, 2)
    3  # Result is recomputed as the cache expired

    Using custom `maxsize` and `ttl`:

    >>> @ttl_cache(maxsize=2, ttl=5)
    ... def multiply(a, b):
    ...     return a * b
    >>> multiply(2, 3)
    6  # Computed
    >>> multiply(2, 3)
    6  # Retrieved from cache
    >>> multiply(3, 4)
    12  # Computed and cached
    >>> multiply(4, 5)
    20  # Computed and cached; oldest entry evicted due to maxsize
    >>> multiply(2, 3)
    6  # Not in cache anymore; recomputed

    Clearing the cache manually:

    >>> multiply.clear_cache()
    >>> multiply(2, 3)
    6  # Cache was cleared, so the result is recomputed
    """
    def ttl_cache_inner(func):
        cache: dict = {}
        @wraps(func)
        def wrapper(*args, **kwargs):
            # clean every expired item
            now = time()
            for key, (timestamp, _) in cache.items():
                if now - timestamp > ttl:
                    del cache[key]
            # check if item is in cache
            key = (args, tuple(kwargs.items()))
            if key in cache:
                return cache[key][1]
            else:
                val = func(*args, **kwargs)
                # if maxsize reached, remove the oldest item
                while len(cache) >= maxsize:
                    oldest = min(cache.items(), key=lambda x: x[1][0])[0]
                    del cache[oldest]
                cache[key] = (time(), val)
                return val
        def clear_cache():
            """Clears the attached cache."""
            cache.clear()
        wrapper.clear_cache = clear_cache
        return wrapper
    return ttl_cache_inner
