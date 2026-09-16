"""Unit tests for the RPCProperty descriptor.

These tests verify :class:`plantimager.commons.RPC.RPCProperty` behavior in
isolation, focusing on the ``auto_notify`` option that emits a notifier signal
whenever a property value changes. The design uses small local classes with a
connected ``RPCSignal`` to observe emissions, covering change-only emission,
the no-notifier and disabled cases, getter-failure handling, the manual
emit-in-setter pattern, and use of the descriptor as a callable decorator.
"""

import unittest
from plantimager.commons.RPC import RPCProperty, RPCSignal


class TestRPCPropertyAutoNotify(unittest.TestCase):
    """Tests for RPCProperty auto-notify and manual notify behavior."""

    def test_auto_notify_emits_only_on_change(self):
        """Auto-notify emits only when the property value actually changes."""
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
        """Auto-notify without a notifier signal does not crash."""
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
        """Auto-notify disabled means no signal is emitted on set."""
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
        """Emit still occurs when the old getter raised and the new one succeeds."""
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
        """Manual emit-in-setter pattern fires only on actual change."""
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
        """RPCProperty can be used as a callable decorator and keeps its notifier."""
        sig = RPCSignal(int)
        prop = RPCProperty(notify=sig, auto_notify=False)

        @prop
        def my_val(self):
            return self._v

        self.assertIsInstance(my_val, RPCProperty)
        self.assertIs(my_val._notifier, sig)


if __name__ == "__main__":
    unittest.main()
