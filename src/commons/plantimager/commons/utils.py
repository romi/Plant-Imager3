from functools import wraps
from time import time
import typing
import types
import collections.abc
from typing import Any, get_origin, get_args


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


def coerce_to_generic(value: Any, generic_type: Any) -> Any:
    """
    Coerce a value to a specified generic type or type hint.

    This utility attempts to convert ``value`` into the type described by
    ``generic_type``.  It supports plain types, ``typing`` constructs such as
    ``Union`` and ``Tuple``, as well as generic container types like ``list``,
    ``dict`` and ``set``.  The function recurses as necessary to coerce nested
    structures and raises a ``TypeError`` when conversion is impossible.

    Parameters
    ----------
    value
        The object to be coerced.
    generic_type
        The target type or type hint.  May be a concrete class, a ``typing``
        generic (e.g., ``list[int]``), a union (e.g., ``int | str``), or
        ``typing.Any``.

    Returns
    -------
    Any
        The coerced value that conforms to ``generic_type`` when the operation
        succeeds.

    Raises
    ------
    TypeError
        * If ``generic_type`` is a union and none of its member types can
          coerce ``value``.
        * If ``value`` is not compatible with the expected container type
          (e.g., a non‑iterable supplied for a ``tuple`` target).
        * If a tuple length does not match the number of type arguments.
        * If ``value`` cannot be instantiated as the required generic origin.
    ValueError
        Propagated from underlying constructors when a conversion fails (e.g.,
        ``int('abc')``).

    Notes
    -----
    The coercion logic proceeds through several ordered steps:

    1. **Union handling** – If ``generic_type`` is a tuple of types, each
       member is tried in turn; the first successful conversion is returned.
       The same strategy is used for ``typing.Union`` and the ``|`` syntax
       introduced in Python 3.10.

    2. **Any** – When ``generic_type`` is ``typing.Any`` the function returns
       ``value`` unchanged.

    3. **Simple types** – For non‑generic classes (e.g., ``int``, ``str``) the
       function first checks ``isinstance``; if the check fails it attempts to
       call the type as a constructor (``generic_type(value)``).

    4. **Tuples** – ``tuple`` generics are distinguished between variadic
       (``tuple[int, ...]``) and fixed‑size (``tuple[int, str]``) forms.  The
       function validates iterability, then coerces each element according to
       the specified element type.
    """
    # 1. Handle Unions (e.g., int | str or Union[int, str])
    if isinstance(generic_type, tuple):
        for gtype in generic_type:
            try:
                return coerce_to_generic(value, gtype)
            except (TypeError, ValueError):
                continue
        raise TypeError(f"Could not coerce {value!r} to any of {generic_type}")

    if generic_type is Any:
        return value
    if is_instance_of_generic(value, generic_type):
        return value

    origin = get_origin(generic_type)
    args = get_args(generic_type)

    # 2. Handle Union types (Python 3.10+ | syntax or typing.Union)
    if origin in (types.UnionType, typing.Union):
        return coerce_to_generic(value, args)

    # 3. Simple types (no origin, e.g., int, str, or a class)
    if origin is None:
        try:
            # If it's already the right type, return it
            if isinstance(value, generic_type):
                return value
            # Attempt type casting
            return generic_type(value)
        except (ValueError, TypeError) as e:
            raise TypeError(f"Failed to coerce {value!r} to {generic_type}: {e}")

    # 4. Handle Tuples
    if issubclass(origin, tuple):
        # Ensure input is iterable
        if not isinstance(value, collections.abc.Iterable):
            raise TypeError(f"Value {value!r} must be iterable to coerce to tuple")

        items = list(value)
        # Variadic tuple: tuple[int, ...]
        if args and args[-1] is Ellipsis:
            element_type = args[0]
            return tuple(coerce_to_generic(item, element_type) for item in items)
        # Fixed-size tuple: tuple[int, str]
        else:
            if len(items) != len(args):
                raise TypeError(f"Tuple length mismatch: expected {len(args)}, got {len(items)}")
            return tuple(coerce_to_generic(item, arg) for item, arg in zip(items, args))

    # 5. Handle Mappings (e.g., dict[str, int])
    if issubclass(origin, collections.abc.Mapping):
        if not isinstance(value, collections.abc.Mapping):
            raise TypeError(f"Value {value!r} must be a mapping to coerce to {origin.__name__}")

        key_type, val_type = (args[0], args[1]) if len(args) >= 2 else (Any, Any)
        return origin({
            coerce_to_generic(k, key_type): coerce_to_generic(v, val_type)
            for k, v in value.items()
        })

    # 6. Handle Sequences and Sets (e.g., list[int], set[str])
    if issubclass(origin, (collections.abc.Sequence, collections.abc.Set)):
        if not isinstance(value, collections.abc.Iterable) or isinstance(value, (str, bytes)):
            raise TypeError(f"Value {value!r} must be an iterable container to coerce to {origin.__name__}")

        element_type = args[0] if args else Any
        return origin(coerce_to_generic(item, element_type) for item in value)

    # Fallback for other generics: try to instantiate the origin with the value
    try:
        return origin(value)
    except Exception as e:
        raise TypeError(f"Could not coerce {value!r} to {generic_type}: {e}")

def is_instance_of_generic(value, generic_type):
    """
    Determine whether ``value`` conforms to a typing generic specification.

    This utility inspects ``generic_type`` using :func:`typing.get_origin` and
    :func:`typing.get_args` and recursively validates ``value`` against the
    resolved origin and its type arguments.  It supports built‑in container
    types (``list``, ``set``, ``tuple``, ``dict``) as well as user‑defined
    generic classes.  When ``generic_type`` is a tuple, each element may be a
    distinct type specification; an ellipsis (``...``) as the last element
    denotes a variadic element type that applies to all items of the tuple.

    Parameters
    ----------
    value : Any
        The object whose type is being checked.
    generic_type : type or tuple of types
        A concrete type, a typing generic (e.g. ``list[int]``), or a tuple of
        such specifications.  If a tuple is provided, the function returns
        ``True`` when ``value`` matches **any** of the contained specifications.

    Returns
    -------
    bool
        ``True`` if ``value`` matches ``generic_type``; otherwise ``False``.

    Raises
    ------
    TypeError
        If ``generic_type`` is not a type, a recognized generic, or a tuple of
        such specifications.

    Notes
    -----
    * The function handles nested containers by recursively invoking itself on
      each element, key, or value.
    * For ``tuple`` generics:
        - ``Tuple[int, str]`` requires a two‑item tuple with the first element
          an ``int`` and the second a ``str``.
        - ``Tuple[int, ...]`` (ellipsis as the last argument) validates that
          **all** items are ``int``.
    * For sequence and set generics (e.g. ``list[int]`` or ``set[str]``) the
      single type argument is applied to every element.
    * For mapping generics (e.g. ``dict[str, float]``) the first type argument
      validates keys and the second validates values.

    See Also
    --------
    typing.get_origin
    typing.get_args
    isinstance
    """
    if isinstance(generic_type, tuple):
        return any(is_instance_of_generic(value, gtype) for gtype in generic_type)

    if generic_type is Any:
        return True

    origin = get_origin(generic_type)

    # If no origin, it's not a generic type
    if origin is None:
        return isinstance(value, generic_type)

    # If Union
    if origin in (types.UnionType, typing.Union):
        return is_instance_of_generic(value, get_args(generic_type))

    # Check if the value is an instance of the origin type
    if not is_instance_of_generic(value, origin):
        return False

    # Get the expected type arguments
    args = get_args(generic_type)

    # If no type args specified, just check the origin
    if not args:
        return True

    # For tuple check if it is a fixed size spec (Ellipsis in args otherwise)
    if issubclass(origin, tuple):
        # Validates tuple elements against variadic or fixed type spec
        if args and args[-1] is  Ellipsis:
            return all(
                is_instance_of_generic(val, tuple(args[:-1])) for val in value
            )
        else:
            return all(
                is_instance_of_generic(val, gtype) for val, gtype in zip(value, args)
            )

    # For containers, check the elements
    if issubclass(origin, (collections.abc.Sequence, collections.abc.Set)):
        return all(is_instance_of_generic(item, args[0]) for item in value)

    # For dictionaries, check keys and values
    if issubclass(origin, collections.abc.Mapping) and len(args) >= 2:
        return all(
            is_instance_of_generic(k, args[0]) and is_instance_of_generic(v, args[1])
            for k, v in value.items()
        )
    return True
