"""
OT-2 Jingle Helpers

Plain async functions and melody constants.
NOT tracked by the workflow engine — only Steps (@task) are tracked.
"""

from unitelabs.sdk import Client

INSTRUMENT_NAME = "Opentrons OT-2"

# Ode to Joy — Beethoven's 9th Symphony, 4th movement (public domain).
# Encoded as (frequency_hz, duration_ms) pairs. 0 Hz = rest.
# Tempo: ~100 BPM. Quarter note = 600 ms.
_Q = 600.0  # quarter note
_H = 1200.0  # half note
_DQ = 900.0  # dotted quarter
_E = 300.0  # eighth note

# Note frequencies (Hz)
_C4 = 262.0
_D4 = 294.0
_E4 = 330.0
_F4 = 349.0
_G4 = 392.0

ODE_TO_JOY: list[tuple[float, float]] = [
    # Line 1: E E F G | G F E D | C C D E | E. D D
    (_E4, _Q),
    (_E4, _Q),
    (_F4, _Q),
    (_G4, _Q),
    (_G4, _Q),
    (_F4, _Q),
    (_E4, _Q),
    (_D4, _Q),
    (_C4, _Q),
    (_C4, _Q),
    (_D4, _Q),
    (_E4, _Q),
    (_E4, _DQ),
    (_D4, _E),
    (_D4, _H),
    # Line 2: E E F G | G F E D | C C D E | D. C C
    (_E4, _Q),
    (_E4, _Q),
    (_F4, _Q),
    (_G4, _Q),
    (_G4, _Q),
    (_F4, _Q),
    (_E4, _Q),
    (_D4, _Q),
    (_C4, _Q),
    (_C4, _Q),
    (_D4, _Q),
    (_E4, _Q),
    (_D4, _DQ),
    (_C4, _E),
    (_C4, _H),
    # Line 3: D D E C | D E(e) F(e) E C | D E(e) F(e) E D | C D G
    (_D4, _Q),
    (_D4, _Q),
    (_E4, _Q),
    (_C4, _Q),
    (_D4, _Q),
    (_E4, _E),
    (_F4, _E),
    (_E4, _Q),
    (_C4, _Q),
    (_D4, _Q),
    (_E4, _E),
    (_F4, _E),
    (_E4, _Q),
    (_D4, _Q),
    (_C4, _Q),
    (_D4, _Q),
    (_G4, _H),
    # Line 4 (repeat of lines 1+2)
    (_E4, _Q),
    (_E4, _Q),
    (_F4, _Q),
    (_G4, _Q),
    (_G4, _Q),
    (_F4, _Q),
    (_E4, _Q),
    (_D4, _Q),
    (_C4, _Q),
    (_C4, _Q),
    (_D4, _Q),
    (_E4, _Q),
    (_E4, _DQ),
    (_D4, _E),
    (_D4, _H),
    (_E4, _Q),
    (_E4, _Q),
    (_F4, _Q),
    (_G4, _Q),
    (_G4, _Q),
    (_F4, _Q),
    (_E4, _Q),
    (_D4, _Q),
    (_C4, _Q),
    (_C4, _Q),
    (_D4, _Q),
    (_E4, _Q),
    (_D4, _DQ),
    (_C4, _E),
    (_C4, _H),
]


async def get_ot2_service(device_name: str):
    """
    Connect to the OT-2 connector service by name.

    Args:
        device_name: UniteLabs service name for the OT-2 connector.

    Returns:
        Tuple of (ot2_service, client).

    Raises:
        ValueError: If the service is not found on the platform.
    """
    client = Client()
    service = await client.get_service_by_name(device_name)
    if service is None:
        msg = f"Service '{device_name}' not found. Check the device name and that it is connected to the platform."
        raise ValueError(msg)
    return service, client
