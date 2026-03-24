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

    def get_model_config(self, model_id: str) -> dict[str, Any]:
        """Get configuration for a specific model."""
        if model_id in self._models:
            return dict(self._models[model_id])

        for key, config in self._models.items():
            if key.startswith(model_id) or model_id.startswith(key):
                return dict(config)

        if "unknown" in self._models:
            _LOGGER.warning("Model %s not found, using unknown model config", model_id)
            return dict(self._models["unknown"])

        _LOGGER.error("Model %s not found and no fallback available", model_id)
        return {}
