"""API client for Philips Air+ integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE_URL,
    DEVICE_ENDPOINT,
    HTTP_USER_AGENT,
    SIGNATURE_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)


class PhilipsAirplusAPIError(Exception):
    """Exception for Philips Air+ API errors."""


class PhilipsAirplusAuthError(PhilipsAirplusAPIError):
    """Exception for authentication failures (HTTP 401/403)."""


class PhilipsAirplusAPIClient:
    """API client for Philips Air+."""

    def __init__(self, hass: HomeAssistant, access_token: str) -> None:
        """Initialize API client."""
        self.hass = hass
        self.access_token = access_token

    def _get_session(self) -> aiohttp.ClientSession:
        """Get HA's shared HTTP session."""
        return async_get_clientsession(self.hass)

    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "User-Agent": HTTP_USER_AGENT,
        }

    async def _fetch_json(self, url: str, timeout: int = 20) -> dict[str, Any]:
        """Fetch JSON from API endpoint."""
        session = self._get_session()
        headers = self._get_headers()

        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 401 or response.status == 403:
                    text = await response.text()
                    raise PhilipsAirplusAuthError(f"HTTP {response.status}: {text}")
                if response.status != 200:
                    text = await response.text()
                    raise PhilipsAirplusAPIError(f"HTTP {response.status}: {text}")

                data: dict[str, Any] = await response.json()
                _LOGGER.debug("API response from %s: %s", url, data)
                return data

        except PhilipsAirplusAuthError:
            raise
        except PhilipsAirplusAPIError:
            raise
        except aiohttp.ClientError as ex:
            raise PhilipsAirplusAPIError(f"Network error: {ex}") from ex
        except json.JSONDecodeError as ex:
            raise PhilipsAirplusAPIError(f"Invalid JSON response: {ex}") from ex

    async def list_devices(self) -> list[dict[str, Any]]:
        """List all devices associated with the account."""
        data = await self._fetch_json(DEVICE_ENDPOINT)
        devices = []

        if isinstance(data, dict):
            if isinstance(data.get("devices"), list):
                devices = data["devices"]
            else:
                for key, value in data.items():
                    if isinstance(value, list) and any(
                        isinstance(item, dict) and item.get("uuid")
                        for item in value
                    ):
                        devices = value
                        break
        elif isinstance(data, list):
            devices = data

        _LOGGER.debug("Found %d devices", len(devices))
        return devices

    async def fetch_signature(self) -> str:
        """Fetch MQTT signature."""
        data: dict[str, Any] = await self._fetch_json(SIGNATURE_ENDPOINT)
        signature: str | None = data.get("signature")

        if not signature:
            raise PhilipsAirplusAPIError("Signature missing in response")

        _LOGGER.debug("Successfully fetched MQTT signature")
        return signature

    async def get_user_info(self) -> dict[str, Any]:
        """Get user information."""
        user_endpoint = f"{API_BASE_URL}/da/user/self"
        data = await self._fetch_json(user_endpoint)
        return data


class PhilipsAirplusDevice:
    """Representation of a Philips Air+ device."""

    __slots__ = ("_data", "_uuid", "_name", "_type")

    def __init__(self, device_data: dict[str, Any]) -> None:
        """Initialize device."""
        self._data = device_data
        self._uuid = self._extract_uuid()
        self._name = self._extract_name()
        self._type = self._extract_type()

    def _extract_uuid(self) -> str:
        """Extract device UUID."""
        return self._data.get("uuid") or self._data.get("id") or "unknown"

    def _extract_name(self) -> str:
        """Extract device name."""
        return (
            self._data.get("name")
            or self._data.get("deviceName")
            or self._data.get("friendlyName")
            or f"Air+ {self._uuid[:8]}"
        )

    def _extract_type(self) -> str:
        """Extract device type."""
        return (
            self._data.get("type")
            or self._data.get("deviceType")
            or self._data.get("ctn")
            or "unknown"
        )

    @property
    def uuid(self) -> str:
        """Get device UUID."""
        return self._uuid

    @property
    def name(self) -> str:
        """Get device name."""
        return self._name

    @property
    def type(self) -> str:
        """Get device type."""
        return self._type

    @property
    def data(self) -> dict[str, Any]:
        """Get raw device data."""
        return self._data

    def __str__(self) -> str:
        """String representation."""
        return f"{self.name} ({self.uuid})"

    def __repr__(self) -> str:
        """Representation."""
        return f"PhilipsAirplusDevice(uuid={self.uuid!r}, name={self.name!r}, type={self.type!r})"


def extract_user_id_from_token(token: str) -> str | None:
    """Extract user ID from JWT token."""
    try:
        import base64

        parts = token.split(".")
        if len(parts) < 2:
            return None

        # Decode the payload (middle part)
        payload = parts[1]
        # Add padding if needed
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        payload_data: dict[str, Any] = json.loads(decoded)

        user_id: str | None = payload_data.get("sub")
        return user_id
    except Exception as ex:
        _LOGGER.debug("Failed to extract user ID from token: %s", ex)
        return None


def extract_expiration_from_token(token: str) -> int | None:
    """Extract expiration timestamp from JWT token."""
    try:
        import base64

        parts = token.split(".")
        if len(parts) < 2:
            return None

        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload + padding)
        payload_data: dict[str, Any] = json.loads(decoded)

        exp: int | None = payload_data.get("exp")
        return exp
    except Exception as ex:
        _LOGGER.debug("Failed to extract expiration from token: %s", ex)
        return None


def build_client_id(user_id: str, device_uuid: str) -> str:
    """Build composite client ID for MQTT connection."""
    import re

    # Track if device_uuid had da- prefix
    has_da_prefix = device_uuid.startswith("da-")

    # Remove da- prefix if present for UUID validation
    if has_da_prefix:
        device_uuid = device_uuid[3:]

    user_id = user_id.strip()

    # UUID regex pattern
    uuid_re = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
    )

    if uuid_re.match(user_id) and uuid_re.match(device_uuid):
        # Restore da- prefix for composite ID
        device_with_prefix = f"da-{device_uuid}"
        composite = f"{user_id}_{device_with_prefix}"
        if len(composite) != 76:  # 36 + 1 + 3 + 36 = 76
            _LOGGER.warning(
                "Composite client ID length %s (expected 76): %s",
                len(composite),
                composite,
            )
        return composite

    # Attempt reconstruction if user_id is 32 hex chars
    hex32_re = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
    if hex32_re.match(user_id) and uuid_re.match(device_uuid):
        user_id_formatted = f"{user_id[0:8]}-{user_id[8:12]}-{user_id[12:16]}-{user_id[16:20]}-{user_id[20:32]}"
        device_with_prefix = f"da-{device_uuid}"
        composite = f"{user_id_formatted}_{device_with_prefix}"
        if len(composite) != 76:
            _LOGGER.warning(
                "Reconstructed composite client ID length %s (expected 76): %s",
                len(composite),
                composite,
            )
        _LOGGER.info(
            "Reconstructed composite client ID from 32-hex user ID: %s", composite
        )
        return composite

    # Fallback
    return f"client-{device_uuid}"
