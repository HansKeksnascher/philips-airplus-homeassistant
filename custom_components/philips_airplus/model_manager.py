"""Model manager for Philips Air+ integration."""
from __future__ import annotations

import logging
import os
from typing import Any

import yaml  # type: ignore[import-untyped]
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class PhilipsAirplusModelManager:
    """Manager for device models."""

    def __init__(self, hass: HomeAssistant, component_path: str) -> None:
        """Initialize the model manager."""
        self._hass = hass
        self._component_path = component_path
        self._models: dict[str, Any] = {}
        self._default_model: str | None = None

    async def async_load_models(self) -> None:
        """Load models from yaml file asynchronously."""
        yaml_path = os.path.join(self._component_path, "models.yaml")

        def _load_yaml():
            """Load YAML file in executor."""
            with open(yaml_path, encoding="utf-8") as f:
                return yaml.safe_load(f)

        try:
            # Run blocking file I/O in executor to avoid blocking event loop
            data = await self._hass.async_add_executor_job(_load_yaml)
            self._models = data.get("models", {})
            self._default_model = data.get("default")
            _LOGGER.debug("Loaded %d models from %s", len(self._models), yaml_path)
        except Exception as ex:
            _LOGGER.error("Failed to load models.yaml: %s", ex)

    def get_model_config(self, model_id: str, detected_model_id: str | None = None) -> dict[str, Any]:
        """Get configuration for a specific model."""
        # Try exact match
        if model_id in self._models:
            model_config: dict[str, Any] = self._models[model_id]
            return model_config

        # Try partial match (model_id is prefix of key, e.g. "AC0651" matches "AC0651/10")
        for key, config in self._models.items():
            if key.startswith(model_id) or model_id.startswith(key):
                model_config = config
                return model_config

        # Fallback to "unknown" model with detected ID in name
        if "unknown" in self._models:
            unknown_config = dict(self._models["unknown"])
            if detected_model_id:
                unknown_config["name"] = f"Philips Air+ {detected_model_id} (Unrecognized Model)"
            _LOGGER.warning("Model %s not found, using unknown model config", model_id)
            return unknown_config

        _LOGGER.error("Model %s not found and no fallback available", model_id)
        return {}

    def get_mode_value(self, model_id: str, mode_name: str) -> int | None:
        """Get value for a specific mode."""
        config = self.get_model_config(model_id)
        modes: dict[str, int] = config.get("modes", {})
        value: int | None = modes.get(mode_name)
        return value

    def get_mode_name(self, model_id: str, mode_value: int) -> str | None:
        """Get name for a specific mode value."""
        config = self.get_model_config(model_id)
        modes: dict[str, int] = config.get("modes", {})
        for name, val in modes.items():
            if val == mode_value:
                return name
        return None
