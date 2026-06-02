# Slot origins (front-left-bottom corner, mm) from opentrons deck definition v3.
SLOT_ORIGINS: dict[int, tuple[float, float]] = {
    1: (0.0, 0.0),
    2: (132.5, 0.0),
    3: (265.0, 0.0),
    4: (0.0, 90.5),
    5: (132.5, 90.5),
    6: (265.0, 90.5),
    7: (0.0, 181.0),
    8: (132.5, 181.0),
    9: (265.0, 181.0),
    10: (0.0, 271.5),
    11: (132.5, 271.5),
    12: (265.0, 271.5),
}

# Fixed trash (slot 12): absolute X, Y of trash bin center opening.
# Derived from opentrons_1_trash_1100ml_fixed well definition + slot 12 origin.
TRASH_X: float = 265.0 + 82.84
TRASH_Y: float = 271.5 + 80.0

# P300 8-Channel GEN2 (right mount = A axis).
# ul_per_mm at 100µL from the piecewise linear calibration in opentrons pipetteModelSpecs.json.
# Default flow rates from opentrons pipetteNameSpecs.json.
P300_UL_PER_MM: float = 18.5
P300_ASPIRATE_FLOW_RATE_UL_S: float = 94.0
P300_DISPENSE_FLOW_RATE_UL_S: float = 94.0

# Movement heights for the right mount (A axis, higher value = higher position).
SAFE_TRAVEL_A: float = 140.0  # clearance for cross-deck lateral moves
APPROACH_CLEARANCE_MM: float = 10.0  # above labware top when positioning over a well
WORKING_CLEARANCE_MM: float = 1.0  # above well bottom for aspirate/dispense
TIP_PRESS_MM: float = 7.0  # mm below labware top to press onto tips

# Calibrated A value (mm) when the right pipette tip is exactly at deck surface (Z = 0).
# To find this value: home the robot, attach a tip, jog the right mount down until
# the tip just contacts the deck, then read A from get_position().
CALIBRATED_DECK_A: float = 50.0  # PLACEHOLDER — measure on your robot before use
