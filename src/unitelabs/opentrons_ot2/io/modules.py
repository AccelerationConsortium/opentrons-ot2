"""
Module detection via /dev/ot_module* symlinks.

Uses the same glob + regex approach as opentrons.hardware_control.module_control.
Module names match each driver class's name() classmethod:
  magdeck, tempdeck, thermocycler, heatershaker
"""

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

# Symlink name → our internal module type key
_MODULE_NAME_MAP = {
    "magdeck": "magnetic",
    "tempdeck": "temperature",
    "thermocycler": "thermocycler",
    "heatershaker": "heater_shaker",
}

# Mirrors MODULE_PORT_REGEX in opentrons.hardware_control.module_control:
# - negative lookbehind suppresses udev tempfiles (.#ot_module_...)
# - negative lookahead suppresses Flex tempfiles (...tmp-cN:N)
_MODULE_PORT_REGEX = re.compile(
    r"(?<!\.#ot_module_)" + "(" + "|".join(_MODULE_NAME_MAP.keys()) + ")" + r"\d+(?!\.tmp-c\d+:\d+)",
    re.IGNORECASE,
)


def scan_module_ports() -> dict[str, str]:
    """
    Return {module_type: port_path} for every module symlink found in /dev.

    Returns an empty dict on non-robot systems where no symlinks exist.
    """
    found: dict[str, str] = {}

    for p in Path("/dev").glob("ot_module*"):
        match = _MODULE_PORT_REGEX.search(p.name)
        if not match:
            continue
        name = match.group(1).lower()
        module_type = _MODULE_NAME_MAP.get(name)
        if module_type:
            log.info("Detected module '%s' at %s", module_type, p)
            found[module_type] = str(p)

    if not found:
        log.info("No OT-2 modules detected in /dev")

    return found
