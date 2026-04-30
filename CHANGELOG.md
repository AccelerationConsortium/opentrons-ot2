# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-17

### Changed

- `MotionControlFeature` now includes GPIO methods (set_button_light, set_rail_lights, read_button, read_door_switch)
- Removed standalone `GPIOControlFeature` in favor of unified motion+GPIO feature
- Redesigned move commands to avoid Optional types (unitelabs-cdk 0.9.0 compatibility)
  - `move_to(position, speed)` - Move all axes to position
  - `move_axis(axis, position, speed)` - Move single axis
  - `move_relative_axis(axis, delta, speed)` - Relative single axis move

### Added

- `HeaterShakerFeature` - SiLA2 feature for Heater-Shaker module (temperature, shaking, latch control)
- `ThermocyclerFeature` - SiLA2 feature for Thermocycler module (lid, plate temperature control)
- `TemperatureModuleFeature` - SiLA2 feature for Temperature Module
- `MagneticModuleFeature` - SiLA2 feature for Magnetic Module (engage/disengage magnets)
- `config/robot_settings.json` - Default OT-2 robot settings

## [0.2.0] - 2026-04-16

### Changed

- **BREAKING**: Refactored IO layer to use Opentrons driver layer instead of direct serial communication
- Replaced custom `SmoothieConnection` with wrapper around `opentrons.drivers.smoothie_drivers.SmoothieDriver`
- Replaced custom `GPIOController` with wrapper around `opentrons.drivers.rpi_drivers.GPIOCharDev`
- Now depends on `opentrons>=8.0.0` package instead of direct `pyserial` implementation

### Added

- `OT2MotionController` - High-level motion controller using proven Opentrons SmoothieDriver
  - Proper homing sequences with current management, unstick moves, and axis ordering
  - Move with backlash compensation and move splitting
  - GPIO control (lights, buttons, door switch)
- `HeaterShakerController` - Wrapper for Heater-Shaker module driver
- `ThermocyclerController` - Wrapper for Thermocycler module driver
- `TemperatureModuleController` - Wrapper for Temperature module driver
- `MagneticModuleController` - Wrapper for Magnetic module driver
- `Temperature` and `RPM` dataclasses for type-safe readings

### Deprecated

- Direct serial implementation moved to `_legacy_direct.py`
- Direct GPIO implementation moved to `_legacy_gpio.py`

## [0.1.0] - 2026-04-16

### Added

- Initial project structure using UniteLabs connector-factory template
- `SmoothieConnection` class for direct GCode serial communication with Smoothie controller
- `SimulatingSmoothieConnection` for testing without hardware
- `GPIOController` class for direct Linux sysfs GPIO control
- `SimulatingGPIOController` for testing without hardware
- `MotionControlFeature` SiLA2 feature with 5 key commands:
  - `home` - Home specified axes (XYZABC)
  - `move` - Move to absolute position
  - `get_position` - Get current axis positions
  - `set_lights` - Control button and rail lights
  - `emergency_stop` - Emergency stop with GPIO reset
- `GPIOControlFeature` SiLA2 feature with GPIO commands:
  - `set_button_light` - RGB button LED control
  - `get_button_light` - Read button LED state
  - `set_rail_lights` - Deck rail light control
  - `get_rail_lights` - Read rail light state
  - `read_button` - Read button press state
  - `read_door_switch` - Read door switch state
- Auto-detection of Smoothie serial port (internal UART /dev/ttyAMA0 on OT-2)
- Configuration options for simulator mode, serial port, and baud rate
- `dist_minimal/ot2_connector.py` - Single-file distribution (12KB)
- `deploy.sh` - Automated deployment script for OT-2 (uses ssh+cat, no scp required)
- `gcode_test.py` - Standalone GCode test script (no SiLA2 dependencies)

### Changed

- Removed `opentrons` package dependency to avoid jsonschema version conflicts
- Implemented direct GCode protocol communication instead of using opentrons drivers
- Dependencies: only `unitelabs-cdk~=0.9.0` and `pyserial>=3.5`

### Tested

- GCode communication verified on OT-2 via /dev/ttyAMA0
- Commands tested: M115 (firmware), M114.2 (position), M119 (limit switches)
