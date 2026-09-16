"""Unit tests for the RPCSignal event mechanism.

These tests exercise :class:`plantimager.commons.RPC.RPCSignal` in isolation,
covering argument type validation and coercion, connection management
(idempotent connect, targeted and full disconnect), weak-reference handling
of dead callbacks, exception propagation, and callback ordering. The design
uses plain in-process callbacks with no sockets so each behavior is verified
deterministically and in isolation.
"""

import unittest
import weakref
from plantimager.commons.RPC import RPCSignal


class TestRPCSignal(unittest.TestCase):
    """Tests for RPCSignal emit, validation, and connection management."""

    def test_emit_coerce(self):
        """Emit coerces arguments to the declared signal types."""
        sig = RPCSignal(int, str)
        out = []
        sig.connect(lambda a, b: out.append((a, b)))
        sig.emit("123", "hi")
        self.assertEqual(out[0], (123, "hi"))

    def test_validate_arity_raises(self):
        """Raises RuntimeError when the argument count mismatches the signal."""
        sig = RPCSignal(int, str)
        with self.assertRaises(RuntimeError):
            sig.validate_args(1)
        with self.assertRaises(RuntimeError):
            sig.emit(1)

    def test_validate_type_without_coerce_raises(self):
        """Raises TypeError when a value does not match without coercion."""
        sig = RPCSignal(int)
        with self.assertRaises(TypeError):
            sig.validate_args("not-an-int", coerce=False)

    def test_validate_coerce_success(self):
        """Coerces a value to the declared type when coerce is enabled."""
        sig = RPCSignal(int)
        self.assertEqual(sig.validate_args("42", coerce=True), (42,))

    def test_connect_idempotent(self):
        """Connecting the same callback twice registers it only once."""
        sig = RPCSignal(int)
        fn = lambda x: None
        sig.connect(fn)
        sig.connect(fn)
        self.assertEqual(len(sig.connections), 1)

    def test_disconnect_specific(self):
        """Disconnecting one callback leaves the others connected."""
        sig = RPCSignal(int)
        fn1 = lambda x: None
        fn2 = lambda x: None
        sig.connect(fn1)
        sig.connect(fn2)
        sig.disconnect(fn1)
        self.assertEqual(len(sig.connections), 1)
        self.assertIn(fn2, sig.connections)

    def test_disconnect_all(self):
        """Disconnecting with no argument clears all connections."""
        sig = RPCSignal(int)
        sig.connect(lambda x: None)
        sig.connect(lambda x: None)
        sig.disconnect()
        self.assertEqual(sig.connections, [])

    def test_weakmethod_gc_skipped(self):
        """Skips dead weak-method callbacks while still firing live ones."""
        class Obj:
            def __init__(self):
                self.seen = None

            def cb(self, x):
                self.seen = x

        obj = Obj()
        sig = RPCSignal(int)
        wm = weakref.WeakMethod(obj.cb)
        sig.connect(wm)
        # keep a strong ref to a second callback to verify dead one is skipped but live still runs
        seen = []
        sig.connect(lambda x: seen.append(x))
        del obj
        # Avoid gc.collect() — it may collect leftover zmq sockets from other tests and hang.
        # WeakMethod should be dead immediately after del; if not, skip the strict check.
        if wm() is not None:
            self.skipTest("WeakMethod not yet dead without gc.collect(), GC timing dependent")
        # should not raise, dead weak ref is skipped, live callback still fires
        sig.emit(1)
        self.assertEqual(seen, [1])

    def test_emit_propagates_exception(self):
        """Exceptions raised by a callback propagate out of emit."""
        def boom(x):
            raise ValueError("boom")

        sig = RPCSignal(int)
        sig.connect(boom)
        with self.assertRaises(ValueError):
            sig.emit(1)

    def test_connect_invalid_type_raises(self):
        """Raises TypeError when connecting a non-callable."""
        sig = RPCSignal(int)
        with self.assertRaises(TypeError):
            sig.connect("not-callable")

    def test_emit_order(self):
        """Callbacks fire in the order they were connected."""
        sig = RPCSignal(int)
        order = []
        sig.connect(lambda x: order.append(1))
        sig.connect(lambda x: order.append(2))
        sig.emit(0)
        self.assertEqual(order, [1, 2])

    def test_multiple_arg_types(self):
        """Signals with multiple declared argument types emit all of them."""
        sig = RPCSignal(int, str, float)
        out = []
        sig.connect(lambda a, b, c: out.append((a, b, c)))
        sig.emit(1, "hi", 3.14)
        self.assertEqual(out[0], (1, "hi", 3.14))


if __name__ == "__main__":
    unittest.main()
