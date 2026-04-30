#!/usr/bin/env python3
"""Simple OT-2 GCode test - no dependencies except pyserial (already on OT-2).

Sends basic GCode commands directly to the Smoothie controller.
"""

import serial
import serial.tools.list_ports
import time

# Smoothie USB identifiers (external USB connection)
SMOOTHIE_VID = 0x04D8
SMOOTHIE_PID = 0xEE93

# Default OT-2 internal UART
DEFAULT_PORT = "/dev/ttyAMA0"

ACK = b"ok\r\nok\r\n"
TERMINATOR = "\r\n\r\n"


def find_smoothie_port():
    """Auto-detect Smoothie serial port."""
    import os

    # Check default OT-2 internal UART first
    if os.path.exists(DEFAULT_PORT):
        return DEFAULT_PORT

    # Search USB serial ports
    for port in serial.tools.list_ports.comports():
        if port.vid == SMOOTHIE_VID and port.pid == SMOOTHIE_PID:
            return port.device

    # Fallback to common USB paths
    for path in ["/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0"]:
        if os.path.exists(path):
            return path
    return None


def send_gcode(ser, command, timeout=30):
    """Send GCode command and wait for response."""
    print(f"  > {command}")
    ser.write(f"{command}{TERMINATOR}".encode())

    response = b""
    start = time.time()
    while ACK not in response:
        if time.time() - start > timeout:
            print(f"  TIMEOUT after {timeout}s")
            break
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            response += chunk
        time.sleep(0.01)

    decoded = response.decode(errors="replace").strip()
    print(f"  < {decoded[:200]}{'...' if len(decoded) > 200 else ''}")
    return decoded


def main():
    print("=== OT-2 GCode Test ===\n")

    # Find port
    port = find_smoothie_port()
    if not port:
        print("ERROR: Smoothie not found. Available ports:")
        for p in serial.tools.list_ports.comports():
            print(f"  {p.device} - {p.description} (VID={p.vid}, PID={p.pid})")
        return

    print(f"Found Smoothie at: {port}\n")

    # Connect
    print("Connecting...")
    ser = serial.Serial(port, 115200, timeout=5)
    time.sleep(2)  # Wait for Smoothie to initialize

    # Clear any startup messages
    if ser.in_waiting:
        ser.read(ser.in_waiting)

    print("Connected!\n")

    # Test commands
    print("1. Get firmware version (M115):")
    send_gcode(ser, "M115")
    print()

    print("2. Get current position (M114.2):")
    send_gcode(ser, "M114.2")
    print()

    print("3. Get limit switch status (M119):")
    send_gcode(ser, "M119")
    print()

    # Home - this actually moves the robot!
    response = input("4. Home all axes? This will move the robot! (y/N): ")
    if response.lower() == "y":
        print("Homing Z, A, B, C first (vertical axes)...")
        send_gcode(ser, "G28.2 ZABC", timeout=120)
        print()

        print("Homing X...")
        send_gcode(ser, "G28.2 X", timeout=60)
        print()

        print("Homing Y...")
        send_gcode(ser, "G28.2 Y", timeout=60)
        print()

        print("Get position after homing:")
        send_gcode(ser, "M114.2")
    else:
        print("Skipped homing.")

    print()

    # Move test
    response = input("5. Test move? (small 10mm Y move) (y/N): ")
    if response.lower() == "y":
        print("Moving Y +10mm...")
        send_gcode(ser, "G0 Y10 F300")
        print()

        print("Get position after move:")
        send_gcode(ser, "M114.2")
        print()

        print("Moving back to Y=0...")
        send_gcode(ser, "G0 Y0 F300")
    else:
        print("Skipped move test.")

    print()
    print("=== Test complete ===")
    ser.close()


if __name__ == "__main__":
    main()
