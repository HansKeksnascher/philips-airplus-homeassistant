# Philips Air+ Home Assistant Integration

A custom Home Assistant integration for controlling Philips Air+ air purifiers via the Versuni cloud API. Forked from [ShorMeneses/philips-airplus-homeassistant](https://github.com/ShorMeneses/philips-airplus-homeassistant) with additional device support, sensors, and tooling.

## Features

- **Fan Control**: Speed control (Auto, Sleep, Turbo)
- **Power Control**: Turn the air purifier on/off
- **Filter Monitoring**: Filter life for replace and clean filters (percentage + hours remaining)
- **Air Quality Sensors**: PM2.5 and Indoor Air Index
- **Maintenance Resets**: Reset filter timers via buttons
- **Re-authentication**: Seamless token refresh without removing the integration
- **MQTT Toggle**: Option to disable cloud connectivity when not needed

## Supported Devices

- Philips Air+ AC0650/10
- Philips Air+ AC0651/10

## Installation

### via HACS (Recommended)

1. Go to HACS > Integrations
2. Click the three dots menu and select "Custom repositories"
3. Add repository: `https://github.com/HansKeksnascher/philips-airplus-homeassistant`
4. Select "Integration" as category
5. Click "Add"
6. Search for "Philips Air+" and install
7. Restart Home Assistant

### Manual Installation

Copy the `custom_components/philips_airplus` directory to your Home Assistant `config/custom_components` directory and restart.

## Configuration

### Prerequisites

A Philips Air+ account with your device set up in the official app.

### Authentication

1. Add the integration in Home Assistant
2. Copy the OAuth login URL from the UI
3. Open in browser, complete login
4. Open DevTools > Network tab
5. Find redirect request: `com.philips.air://loginredirect?code=xxx...`
6. Copy the `code` value and paste into Home Assistant

See the [YouTube walkthrough](https://www.youtube.com/watch?v=bufBp3h0xos) for visual guide.

### Re-authentication

If your token expires, go to **Integration > Configure** and paste a new authorization code. No need to remove/re-add.

## Entities

### Fan
- `air_purifier` - Main fan control

### Sensors
- `pm25` - PM2.5 air quality measurement
- `indoor_air_index` - Indoor Air Index
- `filter_replacement` - Filter replacement life %
- `filter_replacement_hours` - Hours until filter replacement
- `filter_cleaning` - Filter cleaning life %
- `filter_cleaning_hours` - Hours until filter cleaning

### Buttons
- `reset_filter_cleaning` - Reset filter cleaning timer
- `reset_filter_replacement` - Reset filter replacement timer

## Development

Built with Home Assistant 2024.6+ patterns and type hints throughout.

### Tooling
- **Testing**: pytest with `pytest-homeassistant-custom-component`
- **Type checking**: mypy
- **Linting**: ruff
- **Pre-commit hooks**: configured for quality gates

### Running Tests
```bash
source .venv/bin/activate
pytest tests/
```

### Type Checking & Linting
```bash
ruff check custom_components/
mypy custom_components/
```

## Limitations

- Cloud-dependent (requires internet connectivity)
- Only tested with AC0650/10 and AC0651/10 models

## Disclaimer

Third-party implementation based on reverse-engineering the Philips/Versuni API. Not affiliated with Philips or Versuni.

## License

MIT License - See LICENSE file.
