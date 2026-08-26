import unittest
from plantimager.commons.RPC import RPCProperty, RPCSignal


class TestRPCPropertyAutoNotify(unittest.TestCase):
    def test_auto_notify_emits_only_on_change(self):
        sig = RPCSignal(int)
        seen = []
        sig.connect(lambda v: seen.append(v))

        class D:
            def __init__(self):
                self._v = 0

            @RPCProperty(notify=sig, auto_notify=True)
            def val(self):
                return self._v

            @val.setter
            def val(self, v):
                self._v = v

        d = D()
        d.val = 1
        self.assertEqual(seen, [1])
        d.val = 1
        self.assertEqual(seen, [1])

    def test_auto_notify_no_notifier_no_crash(self):
        class D:
            def __init__(self):
                self._v = 0

            @RPCProperty(auto_notify=True)
            def val(self):
                return self._v

            @val.setter
            def val(self, v):
                self._v = v

        d = D()
        d.val = 5
        self.assertEqual(d.val, 5)

    def test_auto_notify_false_no_emit(self):
        sig = RPCSignal(int)
        seen = []
        sig.connect(lambda v: seen.append(v))

        class D:
            def __init__(self):
                self._v = 0

            @RPCProperty(notify=sig, auto_notify=False)
            def val(self):
                return self._v

            @val.setter
            def val(self, v):
                self._v = v

        d = D()
        d.val = 10
        self.assertEqual(seen, [])

    def test_getter_raises_sentinel_still_emits(self):
        sig = RPCSignal(int)
        seen = []
        sig.connect(lambda v: seen.append(v))

        class D:
            def __init__(self):
                self._v = 0
                self._fail_get = True

            @RPCProperty(notify=sig, auto_notify=True)
            def val(self):
                if self._fail_get:
                    raise RuntimeError("getter fail")
                return self._v

            @val.setter
            def val(self, v):
                self._v = v
                self._fail_get = False

        d = D()
        d.val = 7
        # old getter failed -> sentinel, new getter succeeds -> emit should happen
        self.assertIn(7, seen)

    def test_manual_pattern(self):
        sig = RPCSignal(str)

        class D:
            def __init__(self):
                self._p = 0
                self.sig = sig

            @RPCProperty(notify=sig)
            def prop(self):
                return self._p

            @prop.setter
            def prop(self, value):
                if self._p != value:
                    self._p = value
                    self.sig.emit(str(value))

        seen = []
        sig.connect(lambda v: seen.append(v))
        d = D()
        d.prop = 42
        self.assertIn("42", seen)
        seen.clear()
        d.prop = 42
        self.assertEqual(seen, [])

    def test_rpc_property_call_decorator(self):
        sig = RPCSignal(int)
        prop = RPCProperty(notify=sig, auto_notify=False)

        @prop
        def my_val(self):
            return self._v

        self.assertIsInstance(my_val, RPCProperty)
        self.assertIs(my_val._notifier, sig)


if __name__ == "__main__":
    unittest.main()
