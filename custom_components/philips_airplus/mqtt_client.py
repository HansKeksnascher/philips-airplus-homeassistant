"""MQTT client for Philips Air+ integration."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import string
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.client import MQTTMessage

from .const import (
    KEEPALIVE,
    MQTT_HOST,
    MQTT_PATH,
    MQTT_PORT,
    PORT_CONTROL,
    PORT_FILTER_READ,
    PORT_FILTER_WRITE,
    PORT_STATUS,
    PROP_FAN_SPEED,
    PROP_FILTER_CLEAN_RESET_RAW,
    PROP_FILTER_REPLACE_RESET_RAW,
    PROP_MODE,
    TOPIC_CONTROL_TEMPLATE,
    TOPIC_SHADOW_GET_ACCEPTED_TEMPLATE,
    TOPIC_SHADOW_GET_REJECTED_TEMPLATE,
    TOPIC_SHADOW_UPDATE_TEMPLATE,
    TOPIC_STATUS_TEMPLATE,
)

_LOGGER = logging.getLogger(__name__)

FILTER_CLEAN_RESET_HOURS = 720
FILTER_REPLACE_RESET_HOURS = 4800


class PhilipsAirplusMQTTClient:
    """MQTT client for Philips Air+ communication."""

    def __init__(
        self,
        device_id: str,
        access_token: str,
        signature: str,
        client_id: str | None = None,
        custom_authorizer_name: str = "CustomAuthorizer",
    ) -> None:
        """Initialize MQTT client."""
        self.device_id = device_id
        if not self.device_id.startswith("da-"):
            self.device_id = f"da-{device_id}"
        self.access_token = access_token
        self.signature = signature
        self.client_id = client_id or f"ha-{device_id}"
        self.custom_authorizer_name = custom_authorizer_name

        self._client: mqtt.Client | None = None
        self._connection_state: str = "disconnected"
        self._connect_event: threading.Event | None = None
        self._connect_result: bool | None = None
        self._last_disconnect_time: float = 0.0
        self._last_disconnect_rc: int = 0
        self._reconnect_attempts: int = 0
        self._reconnect_base: float = 1.0
        self._reconnect_max_backoff: float = 300.0
        self._rc7_cooldown: float = 120.0
        self._message_callback: Callable[[dict[str, Any]], None] | None = None
        self._connection_callback: Callable[[bool], None] | None = None
        self._shadow_callback: Callable[[dict[str, Any]], None] | None = None
        self._last_nonzero_speed: int = 8
        self._refreshing_credentials: bool = False

        self.outbound_topic = TOPIC_CONTROL_TEMPLATE.format(device_id=self.device_id)
        self.inbound_topic = TOPIC_STATUS_TEMPLATE.format(device_id=self.device_id)

    def set_message_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Set callback for incoming messages."""
        self._message_callback = callback

    def set_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Set callback for connection status changes."""
        self._connection_callback = callback

    def set_shadow_callback(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Set callback for shadow state updates."""
        self._shadow_callback = callback

    def _build_headers(self) -> dict[str, str]:
        """Build WebSocket headers for authentication."""
        return {
            "x-amz-customauthorizer-name": self.custom_authorizer_name,
            "x-amz-customauthorizer-signature": self.signature,
            "tenant": "da",
            "content-type": "application/json",
            "token-header": f"Bearer {self.access_token.strip()}",
            "Sec-WebSocket-Protocol": "mqtt",
        }

    def _on_connect(
        self, client: mqtt.Client, userdata: Any, flags: dict[str, Any], rc: int
    ) -> None:
        """Handle MQTT connection."""
        _LOGGER.info("Connected to MQTT with rc=%s", rc)

        if rc == 0:
            self._connection_state = "connected"
            self._reconnect_attempts = 0
            self._last_disconnect_rc = 0
            self._last_disconnect_time = 0.0
            client.subscribe(self.inbound_topic, qos=0)
            _LOGGER.info("Subscribed to %s", self.inbound_topic)

            shadow_topic = TOPIC_SHADOW_UPDATE_TEMPLATE.format(device_id=self.device_id)
            client.subscribe(shadow_topic, qos=0)
            _LOGGER.info("Subscribed to %s", shadow_topic)

            shadow_get_accepted_topic = TOPIC_SHADOW_GET_ACCEPTED_TEMPLATE.format(device_id=self.device_id)
            client.subscribe(shadow_get_accepted_topic, qos=0)
            _LOGGER.info("Subscribed to %s", shadow_get_accepted_topic)

            shadow_get_rejected_topic = TOPIC_SHADOW_GET_REJECTED_TEMPLATE.format(device_id=self.device_id)
            client.subscribe(shadow_get_rejected_topic, qos=0)
            _LOGGER.info("Subscribed to %s", shadow_get_rejected_topic)

            self._connect_result = True
            if self._connect_event:
                self._connect_event.set()

            if self._connection_callback:
                self._connection_callback(True)
        else:
            self._connection_state = "disconnected"
            self._connect_result = False
            if self._connect_event:
                self._connect_event.set()
            _LOGGER.error("Connection failed with rc=%s", rc)

            if self._connection_callback:
                self._connection_callback(False)

    def _on_message(self, client: mqtt.Client, userdata: Any, msg: MQTTMessage) -> None:
        """Handle incoming MQTT messages."""
        try:
            payload = msg.payload.decode("utf-8")
            message_data = json.loads(payload)

            _LOGGER.debug("Received message on %s: %s", msg.topic, message_data)

            if msg.topic and "shadow" in msg.topic:
                if self._shadow_callback:
                    self._shadow_callback(message_data)
            elif self._message_callback:
                self._message_callback(message_data)

        except json.JSONDecodeError as ex:
            _LOGGER.error("Failed to decode MQTT message: %s", ex)
        except Exception as ex:
            _LOGGER.error("Error processing MQTT message: %s", ex)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        """Handle MQTT disconnect events."""
        _LOGGER.debug("Disconnected from MQTT with rc=%s", rc)
        self._connection_state = "disconnected"
        self._connect_result = False
        if self._connect_event:
            self._connect_event.set()

        if rc != 0:
            _LOGGER.warning("MQTT unexpected disconnect rc=%s", rc)
            self._reconnect_attempts = min(self._reconnect_attempts + 1, 32)
            self._last_disconnect_time = time.time()
            self._last_disconnect_rc = rc
            try:
                client.loop_stop()
            except Exception as ex:
                _LOGGER.debug("Ignoring loop_stop error during disconnect: %s", ex)
            try:
                client.disconnect()
            except Exception as ex:
                _LOGGER.debug("Ignoring disconnect error during disconnect: %s", ex)
            self._client = None

        if self._connection_callback and not self._refreshing_credentials:
            self._connection_callback(False)

    def _blocking_connect_impl(self, timeout: float = 15.0) -> bool:
        """Blocking connect implementation (runs in executor)."""
        try:
            if self._last_disconnect_time and self._last_disconnect_rc != 0:
                elapsed = time.time() - self._last_disconnect_time
                backoff = min(
                    self._reconnect_base * (2 ** max(0, self._reconnect_attempts - 1)),
                    self._reconnect_max_backoff,
                )
                if elapsed < backoff:
                    wait = backoff - elapsed
                    _LOGGER.warning("Throttling reconnect for %.1fs", wait)
                    time.sleep(wait)

            if self._last_disconnect_rc == 7:
                elapsed_since = (
                    time.time() - self._last_disconnect_time
                    if self._last_disconnect_time
                    else None
                )
                if elapsed_since is not None and elapsed_since < self._rc7_cooldown:
                    wait = self._rc7_cooldown - elapsed_since
                    _LOGGER.warning(
                        "Recent rc=7 disconnect; enforcing cooldown for %.1fs", wait
                    )
                    time.sleep(wait)

            headers = self._build_headers()

            self._client = mqtt.Client(
                client_id=self.client_id, transport="websockets", protocol=mqtt.MQTTv311
            )

            self._client.ws_set_options(path=MQTT_PATH, headers=headers)

            self._client.tls_set()

            self._client.on_connect = self._on_connect
            self._client.on_message = self._on_message
            self._client.on_disconnect = self._on_disconnect

            _LOGGER.debug(
                "Connecting to %s:%s with client_id=%s",
                MQTT_HOST,
                MQTT_PORT,
                self.client_id,
            )
            self._client.connect(MQTT_HOST, MQTT_PORT, keepalive=KEEPALIVE)
            self._client.loop_start()

            if self._connect_event is None:
                self._connect_event = threading.Event()
            self._connect_result = None

            if not self._connect_event.wait(timeout=timeout):
                _LOGGER.error("Connection timeout after %.2fs", timeout)
                self._cleanup_client()
                return False

            if self._connect_result is None or not self._connect_result:
                _LOGGER.error("Connection failed (result=%s)", self._connect_result)
                self._cleanup_client()
                return False

            _LOGGER.info("MQTT connected successfully")
            return True

        except Exception as ex:
            _LOGGER.error("Failed during MQTT connect: %s", ex)
            self._cleanup_client()
            return False

    def _cleanup_client(self) -> None:
        """Clean up MQTT client."""
        if self._client:
            try:
                self._client.loop_stop()
            except Exception as ex:
                _LOGGER.debug("Ignoring loop_stop error in cleanup: %s", ex)
            try:
                self._client.disconnect()
            except Exception as ex:
                _LOGGER.debug("Ignoring disconnect error in cleanup: %s", ex)
            self._client = None
        self._connection_state = "disconnected"
        self._connect_result = False

    async def async_connect(self) -> bool:
        """Async connect to MQTT broker."""
        if self._connection_state == "connected":
            return True

        if self._connection_state == "connecting":
            return False

        self._connection_state = "connecting"
        self._connect_event = threading.Event()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._blocking_connect_impl)

    def _sync_disconnect(self) -> None:
        """Synchronous disconnect (runs in executor)."""
        self._cleanup_client()
        _LOGGER.debug("MQTT disconnected")

    async def async_disconnect(self) -> None:
        """Async disconnect from MQTT broker."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._sync_disconnect)

    def disconnect(self) -> None:
        """Disconnect from MQTT broker (sync wrapper)."""
        self._sync_disconnect()

    def is_connected(self) -> bool:
        """Check if MQTT client is connected.

        Returns True during credential refresh to prevent unavailable state
        while reconnecting with new tokens.
        """
        return self._connection_state == "connected" or self._refreshing_credentials

    def _generate_correlation_id(self) -> str:
        """Generate a correlation ID for commands."""
        return "".join(random.choices(string.hexdigits.lower(), k=8))

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    def _build_command_payload(
        self, command_name: str, port_name: str, properties: dict[str, Any]
    ) -> str:
        """Build command payload."""
        payload = {
            "cid": self._generate_correlation_id(),
            "time": self._get_timestamp(),
            "type": "command",
            "cn": command_name,
            "ct": "mobile",
            "data": {"portName": port_name, "properties": properties},
        }
        return json.dumps(payload, separators=(",", ":"))

    def _publish(self, payload: str, topic: str | None = None, qos: int = 0) -> bool:
        """Publish message to MQTT broker."""
        if not self._client or self._connection_state != "connected":
            _LOGGER.error("MQTT client not connected")
            return False

        try:
            publish_topic = topic or self.outbound_topic
            result = self._client.publish(publish_topic, payload, qos=qos)

            if getattr(result, "rc", None) == mqtt.MQTT_ERR_SUCCESS:
                _LOGGER.debug("Published to %s: %s", publish_topic, payload)
                return True
            else:
                _LOGGER.error(
                    "Failed to publish to %s: rc=%s",
                    publish_topic,
                    getattr(result, "rc", None),
                )
                return False

        except Exception as ex:
            _LOGGER.error("Error publishing message: %s", ex)
            return False

    def set_fan_speed(self, speed: int, raw_key: str = PROP_FAN_SPEED) -> bool:
        """Set fan speed using raw property key."""
        if not self.is_connected():
            _LOGGER.error("MQTT not connected")
            return False

        payload = self._build_command_payload("setPort", PORT_CONTROL, {raw_key: speed})

        _LOGGER.debug("Setting fan speed to %s using key %s", speed, raw_key)

        if speed > 0:
            self._last_nonzero_speed = speed

        res = self._publish(payload)

        try:
            self.request_port_status(PORT_STATUS)
        except Exception as ex:
            _LOGGER.debug("Ignoring status request error after set_fan_speed: %s", ex)

        return res

    def set_mode(self, mode: int, raw_key: str = PROP_MODE) -> bool:
        """Set device mode using raw property key."""
        if not self.is_connected():
            _LOGGER.error("MQTT not connected")
            return False

        payload = self._build_command_payload("setPort", PORT_CONTROL, {raw_key: mode})

        _LOGGER.debug("Setting mode to %s using key %s", mode, raw_key)
        success = self._publish(payload)

        try:
            self.request_port_status(PORT_STATUS)
        except Exception as ex:
            _LOGGER.debug("Ignoring status request error after set_mode: %s", ex)

        return success

    def set_power(
        self,
        power_on: bool,
        raw_speed_key: str = PROP_FAN_SPEED,
        raw_power_key: str | None = None,
    ) -> bool:
        """Set power state."""
        if not self.is_connected():
            _LOGGER.error("MQTT not connected")
            return False

        power_val = 1 if power_on else 0
        desired = {"state": {"desired": {"powerOn": True if power_val == 1 else False}}}
        shadow_payload = json.dumps(desired, separators=(",", ":"))

        success = self._publish(
            shadow_payload, topic=f"$aws/things/{self.device_id}/shadow/update"
        )

        if success:
            self.request_port_status(PORT_STATUS)

        return success

    def reset_filter_clean(self) -> bool:
        """Reset clean-filter maintenance timer.

        Resets the filter cleaning timer to 720 hours (30 days).
        """
        if not self.is_connected():
            _LOGGER.error("MQTT not connected")
            return False

        payload = self._build_command_payload(
            "setPort",
            PORT_FILTER_WRITE,
            {PROP_FILTER_CLEAN_RESET_RAW: FILTER_CLEAN_RESET_HOURS},
        )

        _LOGGER.debug("Resetting clean-filter maintenance timer")
        success = self._publish(payload, qos=1)

        try:
            self.request_port_status(PORT_FILTER_READ)
        except Exception as ex:
            _LOGGER.debug("Ignoring filter status request error after reset_filter_clean: %s", ex)
        try:
            self.request_port_status(PORT_STATUS)
        except Exception as ex:
            _LOGGER.debug("Ignoring status request error after reset_filter_clean: %s", ex)

        return success

    def reset_filter_replace(self) -> bool:
        """Reset replace-filter maintenance timer.

        Resets the filter replacement timer to 4800 hours (200 days).
        """
        if not self.is_connected():
            _LOGGER.error("MQTT not connected")
            return False

        payload = self._build_command_payload(
            "setPort",
            PORT_FILTER_WRITE,
            {PROP_FILTER_REPLACE_RESET_RAW: FILTER_REPLACE_RESET_HOURS},
        )

        _LOGGER.debug("Resetting replace-filter maintenance timer")
        success = self._publish(payload, qos=1)

        try:
            self.request_port_status(PORT_FILTER_READ)
        except Exception as ex:
            _LOGGER.debug("Ignoring filter status request error after reset_filter_replace: %s", ex)
        try:
            self.request_port_status(PORT_STATUS)
        except Exception as ex:
            _LOGGER.debug("Ignoring status request error after reset_filter_replace: %s", ex)

        return success

    def request_port_status(self, port_name: str) -> bool:
        """Request status for a specific port."""
        if not self.is_connected():
            _LOGGER.error("MQTT not connected")
            return False

        payload = self._build_command_payload("getPort", port_name, {})

        _LOGGER.debug("Requesting status for port %s", port_name)
        return self._publish(payload)

    def request_all_ports_status(self) -> bool:
        """Request status for all ports."""
        if not self.is_connected():
            _LOGGER.error("MQTT not connected")
            return False

        payload = self._build_command_payload("getAllPorts", "", {})

        _LOGGER.debug("Requesting status for all ports")
        return self._publish(payload)

    def request_shadow_get(self) -> bool:
        """Request AWS IoT shadow get."""
        if not self.is_connected():
            _LOGGER.error("MQTT not connected")
            return False

        shadow_topic = f"$aws/things/{self.device_id}/shadow/get"
        _LOGGER.debug("Requesting shadow get")
        return self._publish("{}", topic=shadow_topic)

    async def async_update_credentials(self, access_token: str, signature: str) -> bool:
        """Update credentials and reconnect.

        Sets _refreshing_credentials flag to maintain availability during reconnection.
        """
        self.access_token = access_token
        self.signature = signature

        if self._connection_state == "connecting":
            _LOGGER.debug("Connect in progress; deferring credential update")
            return False

        self._refreshing_credentials = True
        try:
            await self.async_disconnect()
            await asyncio.sleep(1)
            result = await self.async_connect()
            return result
        finally:
            self._refreshing_credentials = False
