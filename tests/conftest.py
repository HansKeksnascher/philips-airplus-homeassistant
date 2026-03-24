"""Test fixtures for Philips Air+ config flow tests."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

# Add repo root to path so custom_components can be found
repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

from custom_components.philips_airplus.const import DOMAIN


@pytest.fixture
def enable_custom_integrations(hass):
    """Enable custom integrations for testing."""
    return hass


@pytest.fixture
def mock_oauth_authorize_url():
    """Mock OAuth authorize URL generation."""
    with patch(
        "custom_components.philips_airplus.config_flow.PhilipsAirplusOAuth2Implementation.async_generate_authorize_url",
        new_callable=AsyncMock,
        return_value="https://auth.example.com/authorize?client_id=test",
    ) as mock:
        yield mock


@pytest.fixture
def mock_oauth_request_token_success():
    """Mock successful OAuth token request."""
    with patch(
        "custom_components.philips_airplus.config_flow.PhilipsAirplusOAuth2Implementation.async_request_token",
        new_callable=AsyncMock,
        return_value={
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
        },
    ) as mock:
        yield mock


@pytest.fixture
def mock_oauth_request_token_invalid():
    """Mock OAuth token request that returns no access token."""
    with patch(
        "custom_components.philips_airplus.config_flow.PhilipsAirplusOAuth2Implementation.async_request_token",
        new_callable=AsyncMock,
        return_value={},
    ) as mock:
        yield mock


@pytest.fixture
def mock_api_client():
    """Mock API client for listing devices."""
    mock_device = MagicMock()
    mock_device.uuid = "test-device-uuid"
    mock_device.name = "Test Air+ Device"
    mock_device.type = "AC0650/10"

    with patch(
        "custom_components.philips_airplus.config_flow.PhilipsAirplusAPIClient",
        new_callable=MagicMock,
    ) as mock_class:
        mock_instance = MagicMock()
        mock_instance.list_devices = AsyncMock(
            return_value=[
                {
                    "uuid": "test-device-uuid",
                    "name": "Test Air+ Device",
                    "type": "AC0650/10",
                }
            ]
        )
        mock_instance.close = AsyncMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_api_client_no_devices():
    """Mock API client that returns no devices."""
    with patch(
        "custom_components.philips_airplus.config_flow.PhilipsAirplusAPIClient",
        new_callable=MagicMock,
    ) as mock_class:
        mock_instance = MagicMock()
        mock_instance.list_devices = AsyncMock(return_value=[])
        mock_instance.close = AsyncMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_api_client_auth_error():
    """Mock API client that raises auth error."""
    from custom_components.philips_airplus.api import PhilipsAirplusAuthError

    with patch(
        "custom_components.philips_airplus.config_flow.PhilipsAirplusAPIClient",
        new_callable=MagicMock,
    ) as mock_class:
        mock_instance = MagicMock()
        mock_instance.list_devices = AsyncMock(
            side_effect=PhilipsAirplusAuthError("HTTP 401: Unauthorized")
        )
        mock_instance.close = AsyncMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_api_client_connection_error():
    """Mock API client that raises connection error."""
    from custom_components.philips_airplus.api import PhilipsAirplusAPIError

    with patch(
        "custom_components.philips_airplus.config_flow.PhilipsAirplusAPIClient",
        new_callable=MagicMock,
    ) as mock_class:
        mock_instance = MagicMock()
        mock_instance.list_devices = AsyncMock(
            side_effect=PhilipsAirplusAPIError("Network error")
        )
        mock_instance.close = AsyncMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_auth_success():
    """Mock successful auth initialization."""
    with patch(
        "custom_components.philips_airplus.config_flow.PhilipsAirplusAuth",
        new_callable=MagicMock,
    ) as mock_class:
        mock_instance = MagicMock()
        mock_instance.initialize = AsyncMock(return_value=True)
        mock_instance.close = AsyncMock()
        mock_instance.user_id = "test-user-id"
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_auth_failure():
    """Mock failed auth initialization."""
    with patch(
        "custom_components.philips_airplus.config_flow.PhilipsAirplusAuth",
        new_callable=MagicMock,
    ) as mock_class:
        mock_instance = MagicMock()
        mock_instance.initialize = AsyncMock(return_value=False)
        mock_instance.close = AsyncMock()
        mock_class.return_value = mock_instance
        yield mock_instance
