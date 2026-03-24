"""Tests for Philips Air+ config flow."""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.philips_airplus.api import PhilipsAirplusAuthError, PhilipsAirplusAPIError


async def test_oauth_flow_shows_form(hass: HomeAssistant, mock_oauth_authorize_url) -> None:
    """Test that OAuth step shows form with instructions."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "oauth"
    assert "instructions" in result["description_placeholders"]


async def test_oauth_missing_code_shows_error(
    hass: HomeAssistant, mock_oauth_authorize_url
) -> None:
    """Test that missing auth code shows missing_code error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_code": ""},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "missing_code"}


async def test_oauth_invalid_token_shows_error(
    hass: HomeAssistant,
    mock_oauth_authorize_url,
    mock_oauth_request_token_invalid,
    mock_api_client,
) -> None:
    """Test that missing access token shows invalid_token error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_code": "test_code"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_token"}


async def test_oauth_auth_error_shows_invalid_token(
    hass: HomeAssistant,
    mock_oauth_authorize_url,
    mock_oauth_request_token_success,
    mock_api_client_auth_error,
) -> None:
    """Test that auth error (401/403) shows invalid_token error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_code": "test_code"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_token"}


async def test_oauth_connection_error_shows_cannot_connect(
    hass: HomeAssistant,
    mock_oauth_authorize_url,
    mock_oauth_request_token_success,
    mock_api_client_connection_error,
) -> None:
    """Test that connection error shows cannot_connect error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_code": "test_code"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_oauth_no_devices_shows_error(
    hass: HomeAssistant,
    mock_oauth_authorize_url,
    mock_oauth_request_token_success,
    mock_api_client_no_devices,
) -> None:
    """Test that no devices found shows no_devices error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_code": "test_code"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices"}


async def test_oauth_flow_success_with_device_selection(
    hass: HomeAssistant,
    mock_oauth_authorize_url,
    mock_oauth_request_token_success,
    mock_api_client,
    mock_auth_success,
) -> None:
    """Test successful OAuth flow with device selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_code": "test_code"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "select_device"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"device": "0"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Air+ Device"
    assert result["data"]["device_uuid"] == "test-device-uuid"
    assert result["data"]["device_name"] == "Test Air+ Device"


async def test_select_device_invalid_index_aborts(
    hass: HomeAssistant,
    mock_oauth_authorize_url,
    mock_oauth_request_token_success,
    mock_api_client,
    mock_auth_success,
) -> None:
    """Test that invalid device index aborts the flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_code": "test_code"},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"device": "99"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_device"


async def test_select_device_auth_failure_aborts(
    hass: HomeAssistant,
    mock_oauth_authorize_url,
    mock_oauth_request_token_success,
    mock_api_client,
    mock_auth_failure,
) -> None:
    """Test that auth failure aborts the flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"auth_code": "test_code"},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"device": "0"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "auth_failed"


async def test_reauth_flow_initiates(hass: HomeAssistant) -> None:
    """Test that reauth flow initiates correctly."""
    mock_entry = MagicMock()
    mock_entry.entry_id = "test_entry_id"
    mock_entry.data = {
        "device_uuid": "test-uuid",
        "device_name": "Test Device",
    }

    with patch.object(
        hass.config_entries, "async_get_entry", return_value=mock_entry
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": "test_entry_id",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "oauth"
