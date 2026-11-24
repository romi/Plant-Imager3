"""Qt bridge publishing picamera lifecycle commands over MQTT.

Single instance owned by ``AppBridge`` (see its ``mqtt`` property and
``sendCameraCommand`` / ``sendFleetCommand`` slots). QML reaches the
bridge through ``AppBridge.mqtt``: the header dot binds to
``connected``, and (from step 4 of the plan) the camera control panel
calls the ``AppBridge`` send slots.

Connection behavior
-------------------
``start()`` connects asynchronously in a paho background thread and
never raises, so the controller boots offline rather than hanging when
the broker or the ``paho-mqtt`` dependency is missing. Disconnects
clear ``connected`` (red dot); paho then backs off and reconnects on
its own (1s to 30s delays). ``paho-mqtt`` is imported lazily inside
``start()`` for the same reason.

Threading
---------
paho invokes ``_on_connect`` / ``_on_disconnect`` on its network
thread. Updating ``connected`` from there is safe: the
``connectedChanged`` notify signal crosses into the GUI thread via
Qt's automatic queued connection, which is what refreshes the QML
dot.
"""

from PySide6.QtCore import Property
from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot
from PySide6.QtQml import QmlElement
from PySide6.QtQml import QmlUncreatable

from plantimager.commons.logging import create_logger
from plantimager.commons.mqtt_utils import broker_url
from plantimager.commons.mqtt_utils import encode_command
from plantimager.commons.mqtt_utils import fleet_topic
from plantimager.commons.mqtt_utils import split_broker_url
from plantimager.commons.mqtt_utils import topic_for

QML_IMPORT_NAME = "PlantImagerApp"
QML_IMPORT_MAJOR_VERSION = 1

logger = create_logger("MqttBridge")


@QmlElement
@QmlUncreatable("MQTT bridge cannot be created from QML")
class MqttBridge(QObject):
    """Publishes picamera lifecycle commands; reports broker state.

    Parameters
    ----------
    parent : QObject, optional
        Qt parent. ``AppBridge`` passes itself so the bridge dies with
        the app.
    broker : str, optional
        ``tcp://host:port`` URL. Defaults to
        :func:`~plantimager.commons.mqtt_utils.broker_url`, i.e. the
        ``MQTT_BROKER`` environment variable or the controller.
    client : optional
        Pre-built MQTT client. Only used by unit tests to stub out the
        broker; production always passes ``None`` and lets :meth:`start`
        create the real paho client.
    """

    connectedChanged = Signal(bool)

    def __init__(self, parent=None, broker=None, client=None):
        super().__init__(parent)
        self._broker = broker or broker_url()
        self._client = client
        self._connected = False

    @Property(bool, notify=connectedChanged)
    def connected(self) -> bool:
        """Whether the broker connection is currently up (header dot)."""
        return self._connected

    def _set_connected(self, value: bool):
        if self._connected != value:
            self._connected = value
            self.connectedChanged.emit(value)

    @Slot()
    def start(self):
        """Connect to the broker in a background thread; never raises.

        Safe to call when paho or the broker is missing: the failure is
        logged and the bridge stays offline (``connected`` False) until
        the next start. Calling it twice is a no-op once a client
        exists.
        """
        if self._client is not None:
            return
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            logger.warning("paho-mqtt missing, MQTT camera control disabled")
            return
        host, port = split_broker_url(self._broker)
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        try:
            client.connect_async(host, port, keepalive=60)
        except Exception as exc:
            logger.warning(f"MQTT broker at {self._broker} unreachable ({exc})")
            return
        client.loop_start()
        self._client = client

    @Slot()
    def stop(self):
        """Disconnect and drop the client; always leaves us offline."""
        client, self._client = self._client, None
        if client is not None:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:
                pass
        self._set_connected(False)

    def _on_connect(self, client, userdata, flags, reason, properties=None):
        """paho connect callback: only code 0 means we are online.

        ``reason`` is a ``ReasonCode`` under paho v2 but a plain int
        under v1, hence the duck-typed read.
        """
        code = getattr(reason, "getValue", lambda: reason)()
        self._set_connected(code == 0)
        if code != 0:
            logger.warning(f"MQTT broker refused connection (code {code})")

    def _on_disconnect(self, client, userdata, flags, reason, properties=None):
        """paho disconnect callback: connectivity is gone, dot goes red."""
        self._set_connected(False)

    def publish(self, topic: str, payload: str) -> bool:
        """Publish one payload, dropping it with a warning when offline.

        Parameters
        ----------
        topic : str
            Full command topic, e.g. from
            :func:`~plantimager.commons.mqtt_utils.topic_for`.
        payload : str
            JSON command built by
            :func:`~plantimager.commons.mqtt_utils.encode_command`.

        Returns
        -------
        bool
            True when handed to paho (QoS 1), False when dropped
            because no connected client exists.
        """
        if self._client is None or not self._connected:
            logger.warning(f"MQTT offline, dropping {topic}")
            return False
        self._client.publish(topic, payload, qos=1)
        return True

    @Slot(str, str, result=bool)
    def publishCommand(self, hostname: str, action: str) -> bool:
        """Publish one lifecycle command to one picamera.

        Parameters
        ----------
        hostname : str
            Camera Pi hostname (the same name it registers with).
        action : str
            One of ``restart_service``, ``reboot``,
            ``poweroff``. Unknown actions are refused without
            publishing anything.

        Returns
        -------
        bool
            True when published, False when offline or refused.
        """
        try:
            payload = encode_command(action)
        except ValueError:
            logger.warning(f"refusing unknown MQTT action {action!r}")
            return False
        return self.publish(topic_for(hostname), payload)

    @Slot(str, result=bool)
    def publishAll(self, action: str) -> bool:
        """Publish one lifecycle command to every picamera at once.

        Parameters
        ----------
        action : str
            Same actions as :meth:`publishCommand`. Note the fleet
            topic includes the one-way actions, so QML callers must
            confirm ``reboot``/``poweroff`` before invoking this.

        Returns
        -------
        bool
            True when published, False when offline or refused.
        """
        try:
            payload = encode_command(action)
        except ValueError:
            logger.warning(f"refusing unknown MQTT action {action!r}")
            return False
        return self.publish(fleet_topic(), payload)
