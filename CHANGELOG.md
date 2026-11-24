# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-11-24

### Added

- `MotionControlFeature` — MoveToUnverified and MoveThrough commands to cut per-move overhead
- `MotionControlFeature` — PrepareForAspirate command
- `CalibrationFeature` — general deck and pipette-offset calibration reads over SiLA
- Defined execution errors for module commands
- Range and unit constraints on module command inputs
- `get_device_info` returns a DeviceInfo structure
- Robot server bundled into the self-contained executable; deploy uses the executable only (no venv)
- Simulator mode works on hosts without `gpiod`; smoketest config added
- `verify_ot2.sh` checks the HTTP API and reports every failure instead of stopping at the first

### Changed

- **Breaking:** module status responses are now enums instead of free strings, and module input identifiers were renamed
- Plunger (B/C) lower bound now comes from the attached pipette's drop-tip position
- X past its homed position logs a warning instead of raising; `HOMED_POSITION` is no longer treated as a travel limit
- Removed the unverified 0.0 floor on the Z/A gantry axes
- OT-2 wheels are published as tar.gz to a rolling release

### Fixed

- Axes string pattern (`Home`, `DisengageAxes`) rejected valid input such as `XYZABC` on spec-compliant SiLA clients: SiLA patterns are XML Schema regexes, where `^`/`$` are literal characters, not anchors
- Aspirate/dispense plunger direction was reversed
- Light controller was not populated in `with_robot_server` mode
- Simulator position and homed state now stay in sync with SiLA-driven motion
- Deploy: stop the connector before overwriting its binary, guard against duplicate processes, and redirect PyInstaller extraction away from `/tmp`
- Build: missing system packages (sqlite, bz2, lzma, gdbm, build-essential, git) and pinned dependency fixes

## [0.5.0] - 2026-06-11

### Changed

- Motion bounds, shared-hardware module features, and plunger home-current fix (see tag `v0.5.0`)

## [0.4.0] - 2026-05-26

### Added

- `PipetteFeature` — GetAttachedPipettes and ConfigureMount via SiLA2
- `CalibrationFeature` — raw Smoothie EEPROM write commands for axis calibration
- `MotionControlFeature` extensions: axis bounds validation, motor current management, BoardRevision, SerialNumber, DisengageAxes, aspirate/dispense commands
- Dynamic module feature loading at startup via `/dev/ot_module*` scan (heater-shaker, thermocycler, temperature, magnetic)
- `with_robot_server=True` mode: in-process opentrons HTTP robot-server sharing one HardwareAPI and serial port with the SiLA2 gRPC server via `HardwareProxy` and `asyncio.Lock`
- `HardwareProxy` shim for in-process driver sharing between `OT2MotionController` and robot_server
- HTTP + gRPC integration test suite running against the simulator in CI
- Two CI matrix targets: Python 3.10/opentrons 8.8.1 and Python 3.12/opentrons 9.0.0
- Self-contained ARM wheel bundle for OT-2 deployment
- Tailscale setup script

### Changed

- **Enum-based API throughout**: replaced all magic axis/mount string literals with `Axis` and `Mount` enums across feature and IO layers; SiLA2 parameters and responses now use Set constraints instead of unvalidated strings, giving clients introspectable valid values and preventing invalid inputs at the protocol level
- `.pyc` bytecode now precompiled into `/var/cache/sila2-pycache` at deploy time (eliminates 39-minute cold start caused by read-only `/usr/lib` filesystem on OT-2)

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
