#!/usr/bin/env python3
"""Test the GPIOController class from the io module."""

import importlib.util

# Load gpio module directly
spec = importlib.util.spec_from_file_location("gpio_io", "/root/ot2_sila2/src/unitelabs/opentrons_ot2/io/gpio.py")
gpio_io = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gpio_io)

GPIOController = gpio_io.GPIOController


def main():
    print("=== Testing GPIOController ===\n")

    gpio = GPIOController()

    print("1. Setting up GPIO...")
    try:
        gpio.setup()
        print("   Setup complete\n")
    except Exception as e:
        print(f"   Setup failed: {e}")
        print("   (This is expected if GPIO sysfs isn't available)\n")
        return

    print("2. Reading door switch:")
    try:
        door = gpio.read_door_switch()
        print(f"   Door closed: {door}\n")
    except Exception as e:
        print(f"   Failed: {e}\n")

    print("3. Reading button:")
    try:
        button = gpio.read_button()
        print(f"   Button pressed: {button}\n")
    except Exception as e:
        print(f"   Failed: {e}\n")

    print("4. Testing button light (blue):")
    try:
        gpio.set_button_light(blue=True)
        state = gpio.get_button_light()
        print(f"   Button light state: R={state[0]} G={state[1]} B={state[2]}\n")
    except Exception as e:
        print(f"   Failed: {e}\n")

    print("5. Testing rail lights:")
    try:
        gpio.set_rail_lights(True)
        state = gpio.get_rail_lights()
        print(f"   Rail lights on: {state}\n")
    except Exception as e:
        print(f"   Failed: {e}\n")

    # Turn off lights
    try:
        gpio.set_button_light(red=False, green=False, blue=False)
        gpio.set_rail_lights(False)
        print("6. Lights turned off\n")
    except:
        pass

    print("=== Test Complete ===")


if __name__ == "__main__":
    main()
