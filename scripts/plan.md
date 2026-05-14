# Plan of Attack

## 1. Dynamic module feature loading

**Notes item:** dynamic building for optional module features (thermocycler, etc...)

**What Opentrons does internally:**
The HTTP API does expose `GET /modules` (robot-server/robot_server/modules/router.py), but we do not use it. Internally, Opentrons uses the exact same mechanism we should replicate:

1. **udev creates symlinks** in `/dev` named `ot_module_<type><N>` (e.g. `/dev/ot_module_thermocycler0`, `/dev/ot_module_tempdeck1`, `/dev/ot_module_heater_shaker0`, `/dev/ot_module_magdeck0`). These are created by udev rules when a module is plugged in via USB.
2. **Glob `/dev/ot_module*`** at startup (`hardware_control/module_control.py:349` — `AttachedModulesControl.scan()`). Parse symlink names with a regex to identify module type.
3. **Open a direct serial connection** to each detected module. Modules communicate independently of the Smoothie — they are separate USB serial devices.
4. **Hotplug via aionotify** — watch `/dev` for `ot_module_*` CREATE/DELETE events to handle modules plugged in after startup.

The Smoothie is not involved in module detection at all.

**Work:** At connector startup in `create_app()` (`__init__.py:37`), glob `/dev/ot_module*`, parse the names to identify which modules are present, and conditionally register the corresponding SiLA features (`HeaterShakerFeature`, `ThermocyclerFeature`, `TemperatureFeature`, `MagneticFeature`). The feature files in `src/.../features/` already exist but are never registered. Wire each feature to its IO class (`io/heater_shaker.py`, etc.) which opens the appropriate serial port. In simulate mode, skip the glob and register no module features (or all, with simulators).

---

## 2. Document and clarify the two config files

**Notes item:** config question — what is the difference between the two config files
**Checkbox:** Mark to review robot settings configuration to determine which values are actually configurable vs. fixed

**Work:** `ot2_config.json` drives the SiLA connector (server identity, cloud endpoint, discovery, logging, `use_simulator`, `serial_port`). `robot_settings.json` contains OT-2 hardware constants (`model`, `serial_speed`, etc.) that feed into `opentrons.config.robot_configs`. Determine which fields in `robot_settings.json` are actually read by `load_ot2()` vs. unused. Write a short note in README or inline docs. Remove dead fields.

---

## 3. Smoothie driver simulation mode — document and test

**Notes item:** smoothie driver simulation mode — what does the driver itself do / support when no connection is passed
**Checkbox:** Mark to examine smoothie driver simulation capabilities and test in pipeline

**Work:** Audit what `SmoothieDriver(connection=None)` actually does — which calls pass through, which raise, which return mock data. Then add a CI-runnable simulation test (`tests/`) that runs the full connector in simulate mode and exercises all motion endpoints, confirming no hardware required.

---

## 4. Aspirate / dispense on the connector

**Notes items:** aspirate command on the connector itself? + liquid classes should be on client not on host
**Checkbox:** Mark to implement and test liquid handling commands (aspirate/dispense) beyond basic motion

**Work:** Add `aspirate(volume_ul, flow_rate_ul_s)` and `dispense(volume_ul, flow_rate_ul_s)` commands to `MotionControlFeature`. These translate to raw B/C plunger axis moves using the Smoothie. Liquid classes (sequence logic, blowout, mix, touch-tip) stay client-side — the connector only exposes the primitive moves. Document this boundary clearly.

---

## 5. Calibration control

**Notes item:** calibration control

**Work:** Add a `CalibrationController` feature that exposes: probe tip (already exists as `probe` command, may move here), save calibration point, load saved offset, clear calibration. Needs a storage mechanism (JSON file on robot or connector side).

---

## 6. Labware definitions

**Notes item:** labware defs?

**Work:** Decide architecture: either serve OT-2's built-in labware defs via a `LabwareProvider` feature, or leave labware as client-only concern. Concrete first step: query `GET /labware/definitions` from OT-2 HTTP API and expose as a SiLA property or command. Client then uses these to compute well coordinates.

---

## 7. HTTP API coexistence

**Notes item:** do not kill opentrons HTTP API but allow for both to co-exist

**Work:** Currently `start_connector.sh` stops `opentrons-robot-server`. The conflict is serial port ownership (Smoothie `/dev/ttyAMA0`). Evaluate: can the HTTP API and our connector share via the TCP proxy approach, or does the port need to be owned by one process? If TCP proxy is viable (item 8 below), this resolves itself. Otherwise, document why they can't coexist directly and what the trade-off is.

---

## 8. TCP proxy architecture for deployment

**Notes items:** ease of deployment (yocto bake? remove need to ssh into opentrons)
**Checkbox:** Mark to explore TCP proxy architecture suggested by Terence for easier deployment and flexibility between HTTP API and connector

**Work:** Prototype a thin TCP proxy that runs on the OT-2 — accepting gRPC from external clients and forwarding to the connector running locally, while keeping HTTP API alive. Alternatively, investigate whether the connector can talk to the OT-2 HTTP API instead of direct serial, which would eliminate port conflicts entirely and allow the connector to run off-robot.

---

## 9. Device output embedded in test pipeline

**Notes item:** embedding direct output from device in test pipeline to confirm proper connector interaction

**Work:** Add integration tests that spin up the connector in simulate mode, make real gRPC calls via the SiLA client SDK, and assert on the structured response values — not just "no exception". This confirms the full connector → driver → response chain is wired correctly, not just that the driver doesn't crash.

---

## 10. Peripheral driver tests (heater shaker, thermocycler)

**Checkbox:** Mark to test peripheral drivers (heater shaker, thermocycler) when hardware becomes available

**Work:** The feature files exist (`features/heater_shaker.py`, `features/thermocycler.py`). Add simulation-mode tests for each using the `io/heater_shaker.py` and `io/thermocycler.py` IO layers. Mark hardware-only tests with a `@pytest.mark.hardware` skip marker so they don't block CI.

---

## Suggested order

3 → 9 → 4 → 7/8 → 1 → 5 → 6 → 10 → 2

Start with simulation/testing (3, 9) since those unblock everything else without needing hardware. Then aspirate/dispense (4), then the coexistence/deployment question (7, 8) since that architectural answer affects 1. Items 5, 6, 10 are lower priority or hardware-dependent.
