"""Sensor entities for Philips Air+ integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    PERCENTAGE,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
)
from .coordinator import PhilipsAirplusDataCoordinator

_LOGGER = logging.getLogger(__name__)

# Sensor descriptions
SENSOR_DESCRIPTIONS: list[SensorEntityDescription] = [
    SensorEntityDescription(
        key="filter_replace_percentage",
        translation_key="filter_replace_percentage",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:air-filter",
    ),
    SensorEntityDescription(
        key="filter_replace_hours_remaining",
        translation_key="filter_replace_hours_remaining",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:air-filter",
    ),
    SensorEntityDescription(
        key="filter_clean_percentage",
        translation_key="filter_clean_percentage",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:air-filter",
    ),
    SensorEntityDescription(
        key="filter_clean_hours_remaining",
        translation_key="filter_clean_hours_remaining",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfTime.HOURS,
        icon="mdi:air-filter",
    ),
    SensorEntityDescription(
        key="pm25",
        translation_key="pm25",
        name="PM2.5",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        icon="mdi:air-filter",
    ),
    SensorEntityDescription(
        key="indoor_air_index",
        translation_key="indoor_air_index",
        name="Indoor Air Index",
        icon="mdi:air-humidifier",
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Philips Air+ sensors."""
    coordinator = entry.runtime_data

    entities = []
    for description in SENSOR_DESCRIPTIONS:
        entities.append(PhilipsAirplusSensor(coordinator, entry, description))

    async_add_entities(entities)


class PhilipsAirplusSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Philips Air+ sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PhilipsAirplusDataCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.coordinator: PhilipsAirplusDataCoordinator = coordinator
        self.entry = entry
        self.entity_description = description

        # Use stable unique_id based on device UUID so entity registry matches
        self._attr_unique_id = f"{entry.data['device_uuid']}_{description.key}"
        self._attr_device_info: DeviceInfo = {
            "identifiers": {(DOMAIN, entry.data["device_uuid"])},
            "name": entry.data["device_name"],
            "manufacturer": "Philips",
            "model": self.coordinator.model_config.get("name", "Air+ Device"),
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.is_connected

    @property
    def native_value(self) -> str | int | float | None:
        """Return the native value of the sensor."""
        key = self.entity_description.key

        if key.startswith("filter_"):
            # Filter data from filter_info
            if self.coordinator.data:
                filter_info: dict[str, Any] = self.coordinator.data.get(
                    "filter_info", {}
                )
                value: str | int | float | None = filter_info.get(
                    key.replace("filter_", "")
                )
                return value

        if key in ("pm25", "indoor_air_index"):
            if self.coordinator.data:
                air_quality: dict[str, Any] = self.coordinator.data.get(
                    "air_quality_info", {}
                )
                return air_quality.get(key)

        return None

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        key = self.entity_description.key
        attributes = {}

        if key.startswith("filter_") and self.coordinator.data:
            # Add filter hours total if available (use calculated filter_info from coordinator data)
            filter_info = self.coordinator.data.get("filter_info", {})
            if key == "filter_replace_percentage":
                if "replace_hours_total" in filter_info:
                    attributes["total_hours"] = filter_info["replace_hours_total"]
            elif key == "filter_clean_percentage":
                if "clean_hours_total" in filter_info:
                    attributes["total_hours"] = filter_info["clean_hours_total"]

        return attributes
