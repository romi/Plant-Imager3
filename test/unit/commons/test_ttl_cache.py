import unittest
from unittest import mock
from plantimager.commons.utils import ttl_cache


class TestTTLCache(unittest.TestCase):
    def test_basic_hit(self):
        calls = []

        @ttl_cache(maxsize=16, ttl=300)
        def f(x):
            calls.append(x)
            return x * 2

        self.assertEqual(f(1), 2)
        self.assertEqual(f(1), 2)
        self.assertEqual(len(calls), 1)

    def test_kwargs_key_diff(self):
        calls = []

        @ttl_cache(maxsize=16, ttl=300)
        def f(a, b=0):
            calls.append((a, b))
            return a + b

        self.assertEqual(f(1, b=2), 3)
        self.assertEqual(f(1, b=3), 4)
        self.assertEqual(len(calls), 2)
        # repeat first
        self.assertEqual(f(1, b=2), 3)
        self.assertEqual(len(calls), 2)

    def test_expiry_recomputes(self):
        calls = []

        @ttl_cache(maxsize=10, ttl=10)
        def f(x):
            calls.append(1)
            return x * 2

        with mock.patch("plantimager.commons.utils.time", return_value=100.0):
            self.assertEqual(f(1), 2)
            self.assertEqual(len(calls), 1)
        with mock.patch("plantimager.commons.utils.time", return_value=105.0):
            self.assertEqual(f(1), 2)
            self.assertEqual(len(calls), 1)  # still cached
        with mock.patch("plantimager.commons.utils.time", return_value=200.0):
            self.assertEqual(f(1), 2)
            self.assertEqual(len(calls), 2)  # expired, recomputed
        with mock.patch("plantimager.commons.utils.time", return_value=200.0):
            self.assertEqual(f(1), 2)
            self.assertEqual(len(calls), 2)  # cached again

    def test_expiry_cleans_multiple_without_runtime_error(self):
        # utils.py: for key, (timestamp, _) in cache.items(): del cache[key] -> RuntimeError if >1 expired
        # This test should fail before fix, pass after fix (list(cache.items())).
        with mock.patch("plantimager.commons.utils.time") as mock_time:
            mock_time.return_value = 100.0

            @ttl_cache(maxsize=10, ttl=10)
            def f(x):
                return x

            f(1)
            f(2)
            f(3)
            mock_time.return_value = 200.0
            # all three expired, next call iterates over dict while deleting
            try:
                self.assertEqual(f(4), 4)
            except RuntimeError as e:
                self.fail(f"ttl_cache expiry cleanup raised RuntimeError: {e}")

    def test_lru_eviction(self):
        calls = []

        @ttl_cache(maxsize=2, ttl=300)
        def g(x):
            calls.append(x)
            return x

        with mock.patch("plantimager.commons.utils.time", side_effect=[1, 1, 2, 2, 3, 3]):
            g(1)  # t=1
            g(2)  # t=2 cache full [1,2]
            g(3)  # t=3 evicts oldest (1) -> [2,3]
        calls.clear()
        with mock.patch("plantimager.commons.utils.time", return_value=4):
            g(1)
            self.assertIn(1, calls)  # 1 was evicted, recomputed
            calls.clear()
            g(2)
            self.assertIn(2, calls)  # 2 was evicted after previous insert
            calls.clear()
            g(3)
            # need to check cache state: after reinserting 1 and 2, 3 was evicted
            self.assertIn(3, calls)

    def test_clear_cache_attr(self):
        @ttl_cache()
        def f(x):
            return x

        self.assertTrue(hasattr(f, "clear_cache"))
        f(1)
        f.clear_cache()
        # after clear, next call should recompute
        calls = []

        @ttl_cache()
        def g(x):
            calls.append(1)
            return x

        g(1)
        g.clear_cache()
        g(1)
        self.assertEqual(len(calls), 2)

    def test_preserves_wrapped_name(self):
        @ttl_cache()
        def my_func():
            pass

        self.assertEqual(my_func.__name__, "my_func")

    def test_ttl_cache_with_no_args(self):
        calls = []

        @ttl_cache(maxsize=4, ttl=300)
        def f():
            calls.append(1)
            return 42

        self.assertEqual(f(), 42)
        self.assertEqual(f(), 42)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
