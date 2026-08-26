import unittest
import weakref
from plantimager.commons.RPC import RPCSignal


class TestRPCSignal(unittest.TestCase):
    def test_emit_coerce(self):
        sig = RPCSignal(int, str)
        out = []
        sig.connect(lambda a, b: out.append((a, b)))
        sig.emit("123", "hi")
        self.assertEqual(out[0], (123, "hi"))

    def test_validate_arity_raises(self):
        sig = RPCSignal(int, str)
        with self.assertRaises(RuntimeError):
            sig.validate_args(1)
        with self.assertRaises(RuntimeError):
            sig.emit(1)

    def test_validate_type_without_coerce_raises(self):
        sig = RPCSignal(int)
        with self.assertRaises(TypeError):
            sig.validate_args("not-an-int", coerce=False)

    def test_validate_coerce_success(self):
        sig = RPCSignal(int)
        self.assertEqual(sig.validate_args("42", coerce=True), (42,))

    def test_connect_idempotent(self):
        sig = RPCSignal(int)
        fn = lambda x: None
        sig.connect(fn)
        sig.connect(fn)
        self.assertEqual(len(sig.connections), 1)

    def test_disconnect_specific(self):
        sig = RPCSignal(int)
        fn1 = lambda x: None
        fn2 = lambda x: None
        sig.connect(fn1)
        sig.connect(fn2)
        sig.disconnect(fn1)
        self.assertEqual(len(sig.connections), 1)
        self.assertIn(fn2, sig.connections)

    def test_disconnect_all(self):
        sig = RPCSignal(int)
        sig.connect(lambda x: None)
        sig.connect(lambda x: None)
        sig.disconnect()
        self.assertEqual(sig.connections, [])

    def test_weakmethod_gc_skipped(self):
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
        def boom(x):
            raise ValueError("boom")

        sig = RPCSignal(int)
        sig.connect(boom)
        with self.assertRaises(ValueError):
            sig.emit(1)

    def test_connect_invalid_type_raises(self):
        sig = RPCSignal(int)
        with self.assertRaises(TypeError):
            sig.connect("not-callable")

    def test_emit_order(self):
        sig = RPCSignal(int)
        order = []
        sig.connect(lambda x: order.append(1))
        sig.connect(lambda x: order.append(2))
        sig.emit(0)
        self.assertEqual(order, [1, 2])

    def test_multiple_arg_types(self):
        sig = RPCSignal(int, str, float)
        out = []
        sig.connect(lambda a, b, c: out.append((a, b, c)))
        sig.emit(1, "hi", 3.14)
        self.assertEqual(out[0], (1, "hi", 3.14))


if __name__ == "__main__":
    unittest.main()
