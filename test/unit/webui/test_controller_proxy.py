import unittest
from unittest import mock


class TestControllerProxy(unittest.TestCase):
    def setUp(self):
        from plantimager.webui import controller_proxy

        # save original and reset singleton
        self._orig_instance = getattr(controller_proxy.RPCController, "_instance", None)
        controller_proxy.RPCController._instance = None
        self.addCleanup(self._restore_instance)

    def _restore_instance(self):
        from plantimager.webui import controller_proxy

        controller_proxy.RPCController._instance = self._orig_instance

    @mock.patch("plantimager.webui.controller_proxy.RPCClient.__init__", return_value=None)
    def test_singleton_same_object(self, mock_init):
        from plantimager.webui.controller_proxy import RPCController
        import zmq

        ctx = mock.Mock(spec=zmq.Context)
        # RPCController.__new__ implements singleton, __init__ may be mocked partially
        # Need to also mock zmq usage inside instance creation if needed
        a = RPCController(ctx, "tcp://localhost:14567")
        b = RPCController(ctx, "tcp://localhost:14567")
        self.assertIs(a, b)

    @mock.patch("plantimager.webui.controller_proxy.RPCClient.__init__", return_value=None)
    def test_instance_returns_singleton(self, mock_init):
        from plantimager.webui.controller_proxy import RPCController
        import zmq

        ctx = mock.Mock(spec=zmq.Context)
        created = RPCController(ctx, "tcp://localhost:14567")
        fetched = RPCController.instance()
        self.assertIs(created, fetched)

    def test_instance_without_init_raises(self):
        from plantimager.webui.controller_proxy import RPCController

        with self.assertRaises(RuntimeError):
            RPCController.instance()

    @mock.patch("plantimager.webui.controller_proxy.RPCClient.__init__", return_value=None)
    def test_reset_via_none_allows_new(self, mock_init):
        from plantimager.webui.controller_proxy import RPCController
        import zmq

        ctx = mock.Mock(spec=zmq.Context)
        a = RPCController(ctx, "tcp://localhost:14567")
        RPCController._instance = None
        b = RPCController(ctx, "tcp://localhost:14567")
        self.assertIsNot(a, b)

    @mock.patch("plantimager.webui.controller_proxy.RPCClient.__init__", return_value=None)
    def test_controller_proxy_inherits(self, mock_init):
        from plantimager.webui.controller_proxy import RPCController
        from plantimager.commons.controller_device import ControllerDevice
        from plantimager.commons.RPC import RPCClient

        self.assertTrue(issubclass(RPCController, ControllerDevice))
        self.assertTrue(issubclass(RPCController, RPCClient))


if __name__ == "__main__":
    unittest.main()
