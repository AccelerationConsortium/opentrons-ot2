- dynamic building for optional module features (thermocycler, etc...)
- config question what is the difference between the two config files
- smoothie driver simulation mode what does the driver itself do / support when no connection is passed
- embedding direct output from device in test pipeline to confirm proper connector interaction
- liquid classes should be on client not on host if possible for aspiration code
- aspirate command on the connector itself?
- calibration control
- labware defs?
- do not kill opentrons http API but allow for both to co-exist
- ease of deployment (yocto bake? remove need to ssh into opentrons)

[ ] Mark to explore TCP proxy architecture suggested by Terence for easier deployment and flexibility between HTTP API and connector
[ ] Mark to investigate if OpenTrons exposes endpoint for listing available modules to enable dynamic feature loading
[ ] Mark to examine smoothie driver simulation capabilities and test in pipeline
[ ] Mark to implement and test liquid handling commands (aspirate/dispense) beyond basic motion
[ ] Mark to test peripheral drivers (heater shaker, thermocycler) when hardware becomes available
[ ] Mark to review robot settings configuration to determine which values are actually configurable vs. fixed
[ ] Lukas to send summary notes to Mark
