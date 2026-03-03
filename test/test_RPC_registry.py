import gc
import unittest
import threading
import time
import zmq
import logging
import uuid
from typing import Tuple, Literal

# Adjust imports based on your actual package structure
from plantimager.commons.RPC import (
    RPCClient, RPCServer, RPCSignal, RPCProperty, NoResult, RPCEvents
)
from plantimager.commons.deviceregistry import (
    DeviceRegistry, EventType, ALIVE_TIMEOUT
)


# --- Test Fixtures & Interfaces ---

class TestInterface:
    """Interface definition for testing RPC."""
    signal_something_happened = RPCSignal(str)

    @RPCProperty
    def test_prop(self) -> int:
        pass

    @test_prop.setter
    def test_prop(self, value: int):
        pass

    def echo(self, message: str) -> str:
        pass

    def get_blob(self) -> Tuple[memoryview, dict]:
        pass


class TestDevice(TestInterface, RPCServer):
    """Concrete Server Implementation."""

    def __init__(self, context: zmq.Context, url: str):
        # Reduced timeout for faster tests
        RPCServer.__init__(self, context, url, alive_timeout=2)
        self._prop_val = 0

    @RPCServer.register_method_json(timeout=1000)
    def echo(self, message: str) -> str:
        return f"Echo: {message}"

    @RPCServer.register_method_buffer(timeout=1000)
    def get_blob(self) -> Tuple[memoryview, dict]:
        data = b"\xde\xad\xbe\xef"
        return memoryview(data), {"size": 4, "type": "raw"}

    @RPCProperty(notify=TestInterface.signal_something_happened)
    def test_prop(self) -> int:
        return self._prop_val

    @test_prop.setter
    def test_prop(self, value: int):
        if self._prop_val != value:
            self._prop_val = value
            self.signal_something_happened.emit(str(value))


@RPCClient.register_interface(TestInterface)
class TestClientProxy(TestInterface, RPCClient):
    """Client Proxy Implementation."""

    def __init__(self, context: zmq.Context, url: str):
        # Bypass abstract init calls for simplicity in mixin
        TestInterface.__init__(self)
        RPCClient.__init__(self, context, url)


class BaseRPCTest(unittest.TestCase):
    def setUp(self):
        # Use a fresh context for each test to avoid lingering socket states
        self.context = zmq.Context()
        self.registry_port = 5555
        self.registry_addr = "127.0.0.1"
        self.registry_url = f"tcp://{self.registry_addr}:{self.registry_port}"

        # Suppress noisy logging during tests
        logging.getLogger('RPC').setLevel(logging.CRITICAL)
        logging.getLogger('deviceregistry').setLevel(logging.CRITICAL)

    def tearDown(self):
        gc.collect()
        print(self.context)
        self.context.term()
        self.context = None

    def start_registry(self) -> DeviceRegistry:
        reg = DeviceRegistry(self.context, addr=self.registry_addr, port=str(self.registry_port))
        reg.start()
        time.sleep(0.1)  # Give it a moment to bind
        return reg


# --- Section 1: Core Functionality Tests ---

class TestDeviceRegistryCore(BaseRPCTest):

    def test_registry_lifecycle(self):
        """Test starting registry, registering a device, and unregistering."""
        registry = self.start_registry()

        try:
            # 1. Register Device
            # We simulate the client side of registration manually to check raw protocol
            with self.context.socket(zmq.REQ) as socket:
                socket.connect(self.registry_url)

                # Send Register
                socket.send_json({
                    "event": EventType.REGISTER,
                    "payload": {
                        "device_type": "camera",
                        "addr": "tcp://127.0.0.1:9000",
                        "name": "cam-1",
                        "overwrite": False
                    }
                })
                reply = socket.recv_json()

                self.assertEqual(reply["event"], EventType.REGISTER_ACK)
                self.assertEqual(reply["payload"]["name"], "cam-1")
                uuid_val = reply["payload"]["uuid"]
                self.assertTrue(uuid_val)

                # 2. Verify Internal State
                devices = registry.get_devices()
                self.assertIn("cam-1", devices)
                self.assertEqual(devices["cam-1"], ("camera", "tcp://127.0.0.1:9000"))

                # 3. Unregister
                socket.send_json({
                    "event": EventType.UNREGISTER,
                    "payload": {"uuid": uuid_val}
                })
                reply = socket.recv_json()
                self.assertEqual(reply["event"], EventType.ACK)
                self.assertTrue(reply["payload"]["success"])

                # 4. Verify Removal
                devices = registry.get_devices()
                self.assertNotIn("cam-1", devices)

        finally:
            registry.stop()
            registry.join()

    def test_registry_overwrite_protection(self):
        """Test registration name conflict handling with and without overwrite."""
        registry = self.start_registry()
        try:
            with self.context.socket(zmq.REQ) as socket:
                socket.connect(self.registry_url)

                # Register first device
                socket.send_json({
                    "event": EventType.REGISTER,
                    "payload": {"device_type": "A", "addr": "tcp://1.1.1.1", "name": "device", "overwrite": False}
                })
                socket.recv_json()

                # Register second device same name, overwrite=False
                socket.send_json({
                    "event": EventType.REGISTER,
                    "payload": {"device_type": "B", "addr": "tcp://2.2.2.2", "name": "device", "overwrite": False}
                })
                reply = socket.recv_json()

                # Registry should have renamed the second one
                name_2 = reply["payload"]["name"]
                self.assertNotEqual(name_2, "device")
                self.assertTrue(name_2.startswith("device-"))

                # Register third device, overwrite=True
                socket.send_json({
                    "event": EventType.REGISTER,
                    "payload": {"device_type": "C", "addr": "tcp://3.3.3.3", "name": "device", "overwrite": True}
                })
                reply = socket.recv_json()

                # Should take the name "device"
                self.assertEqual(reply["payload"]["name"], "device")

                # Check that the first device (tcp://1.1.1.1) is gone or replaced
                current_devices = registry.get_devices()
                self.assertEqual(current_devices["device"][1], "tcp://3.3.3.3")

        finally:
            registry.stop()
            registry.join()


class TestRPCProtocol(BaseRPCTest):

    def setUp(self):
        super().setUp()
        self.registry = self.start_registry()
        self.server_port = 9000
        self.server_url = f"tcp://127.0.0.1:{self.server_port}"

        # Setup Server
        self.server = TestDevice(self.context, self.server_url)
        self.server.register_to_registry("test_type", "test_dev", self.registry_url)

        # Run server in thread
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        # Give server time to spin up
        time.sleep(0.2)

    def tearDown(self):
        self.server.stop_server()
        self.server_thread.join()
        self.registry.stop()
        self.registry.join()
        del self.server
        del self.registry
        super().tearDown()

    def test_rpc_method_call_json(self):
        """Test basic JSON method call and return value."""
        client = TestClientProxy(self.context, self.server_url)
        response = client.echo("Hello World")
        self.assertEqual(response, "Echo: Hello World")

    def test_rpc_method_call_buffer(self):
        """Test buffer method call (memoryview transfer)."""
        client = TestClientProxy(self.context, self.server_url)
        data, info = client.get_blob()

        self.assertIsInstance(data, (memoryview, bytes))
        self.assertEqual(bytes(data), b"\xde\xad\xbe\xef")
        self.assertEqual(info["size"], 4)
        del client

    def test_rpc_property_get_set(self):
        """Test property getters and setters."""
        client = TestClientProxy(self.context, self.server_url)

        # Test Initial Value
        self.assertEqual(client.test_prop, 0)

        # Test Setter
        client.test_prop = 42

        # Verify Getter
        self.assertEqual(client.test_prop, 42)

        # Verify Server Internal State
        self.assertEqual(self.server._prop_val, 42)

    def test_rpc_signals(self):
        """Test that server property changes emit signals caught by client."""
        client = TestClientProxy(self.context, self.server_url)

        # Signal capture
        received_signals = []

        def signal_handler(val):
            received_signals.append(val)

        client.signal_something_happened.connect(signal_handler)

        # Trigger signal via property set
        client.test_prop = 100

        # Allow time for signal propagation (ZMQ is async)
        time.sleep(0.2)

        self.assertIn("100", received_signals)

    def test_unknown_method_handling(self):
        """Test client calling a method not exposed by server."""
        # Using raw socket to simulate malicious/broken client
        with self.context.socket(zmq.REQ) as s:
            s.connect(self.server_url)
            s.send_json({
                "event": RPCEvents.METHOD_CALL,
                "method": "non_existent_method",
                "params": {}
            })
            reply = s.recv_json()
            self.assertFalse(reply["success"])
            self.assertIn("not implemented", reply["error"])


# --- Section 2: Robustness Tests (Expected Failures) ---

class TestRobustness(BaseRPCTest):
    """
    Tests scenarios involving connection loss, component restarts, and edge cases.
    These tests are expected to FAIL with the current implementation.
    """

    def setUp(self):
        super().setUp()
        self.registry = self.start_registry()
        self.server_url = "tcp://127.0.0.1:9001"
        self.server = TestDevice(self.context, self.server_url)
        self.server.register_to_registry("test_type", "robust_dev", self.registry_url)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.start()
        time.sleep(0.1)

    def tearDown(self):
        self.server.stop_server()
        self.server_thread.join(timeout=1)
        self.registry.stop()
        self.registry.join()
        del self.server
        del self.registry
        super().tearDown()

    def test_server_recovers_registration_after_registry_restart(self):
        """
        Scenario: Registry crashes and restarts.
        Expected: Server's 'alive check' fails, detects registry loss, and re-registers itself.
        Current Behavior: Server logs error but does not re-register.
        Required Fix: Implement re-registration logic in RPCServer.serve_forever loop when alive_check fails.
        """
        # 1. Verify initial registration
        self.assertIn("robust_dev", self.registry.get_devices())

        # 2. Kill Registry
        self.registry.stop()
        self.registry.join()

        # 3. Start New Registry on same port (Simulate restart)
        # Note: Internal state is lost, so "robust_dev" is unknown to new registry
        self.registry = self.start_registry()
        self.assertNotIn("robust_dev", self.registry.get_devices())

        # 4. Wait for Server to heartbeat (alive_timeout=2s in TestDevice)
        time.sleep(3)

        # 5. Check if Server re-registered
        # This will fail because RPCServer currently just logs "Check Alive failed"
        devices = self.registry.get_devices()
        self.assertIn("robust_dev", devices, "Server failed to re-register after registry restart")

    def test_client_timeout_handling_on_call(self):
        """
        Scenario: Server hangs indefinitely during a method call.
        Expected: Client raises a TimeoutError or specific exception, not just returning False/NoResult.
        Current Behavior: Client returns False or NoResult object which suppresses the exception context.
        Required Fix: Client execute() should raise exceptions for timeouts to allow proper try/except flow.
        """
        # Mock a server freeze
        original_method = self.server.echo

        def hanging_method(self, msg):
            print("A")
            time.sleep(5)  # Longer than client timeout (1s)
            print("B")
            return original_method(msg)
        self.server.echo = hanging_method

        # Monkey patch the instance method
        # Note: This is tricky with RPCServer structure, essentially we simulate a timeout
        # by making the client timeout shorter than server processing.

        client = TestClientProxy(self.context, self.server_url)
        # We need to manually lower the timeout map in the client for this specific test
        client._json_methods['echo'] = 100  # 100ms timeout

        with self.assertRaises(TimeoutError, msg="Client did not raise TimeoutError on server hang"):
            rep = client.echo("Hello")
            print(rep)
        del client

    def test_client_reconnect_after_server_restart(self):
        """
        Scenario: Server process dies and restarts.
        Expected: Client detects broken pipe/timeout, reconnects, and succeeds on subsequent calls.
        Current Behavior: ZMQ REQ/REP gets desynchronized if REP dies in middle. Client inventory is stale.
        Required Fix: Client needs retry logic and potentially re-fetching inventory/handshake on connection errors.
        """
        client = TestClientProxy(self.context, self.server_url)
        self.assertEqual(client.echo("1"), "Echo: 1")

        # Restart Server
        self.server.stop_server()
        self.server_thread.join()

        # Start new server instance on same URL
        new_server = TestDevice(self.context, self.server_url)
        # skip registration for speed, just bind port
        t = threading.Thread(target=new_server.serve_forever)
        t.start()

        try:
            # Client calls again.
            # If the previous socket is stuck awaiting reply, this might hang or fail silently.
            response = client.echo("2")
            self.assertEqual(response, "Echo: 2", "Client failed to communicate with restarted server")
        finally:
            new_server.stop_server()
            t.join()


if __name__ == "__main__":
    unittest.main()