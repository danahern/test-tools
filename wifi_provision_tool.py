#!/usr/bin/env python3
"""BLE WiFi provisioning tool for macOS.

Communicates with the wifi_prov BLE GATT service to:
- Discover devices advertising the provisioning service
- Trigger WiFi AP scans and display results
- Send WiFi credentials for provisioning
- Query connection status and IP address
- Trigger factory reset

Requires: pip install bleak
"""

import argparse
import asyncio
import struct
import sys

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    print("Error: bleak is required. Install with: pip install bleak")
    sys.exit(1)

# UUID base: a0e4f2b0-XXXX-4c9a-b000-d0e6a7b8c9d0
UUID_SVC = "a0e4f2b0-0001-4c9a-b000-d0e6a7b8c9d0"
UUID_SCAN_TRIG = "a0e4f2b0-0002-4c9a-b000-d0e6a7b8c9d0"
UUID_SCAN_RES = "a0e4f2b0-0003-4c9a-b000-d0e6a7b8c9d0"
UUID_CRED = "a0e4f2b0-0004-4c9a-b000-d0e6a7b8c9d0"
UUID_STATUS = "a0e4f2b0-0005-4c9a-b000-d0e6a7b8c9d0"
UUID_RESET = "a0e4f2b0-0006-4c9a-b000-d0e6a7b8c9d0"

SECURITY_NAMES = {
    0: "Open",
    1: "WPA-PSK",
    2: "WPA2-PSK",
    3: "WPA2-PSK-SHA256",
    4: "WPA3-SAE",
}

STATE_NAMES = {
    0: "IDLE",
    1: "SCANNING",
    2: "SCAN_COMPLETE",
    3: "PROVISIONING",
    4: "CONNECTING",
    5: "CONNECTED",
}


def decode_scan_result(data: bytes) -> dict:
    """Decode scan result from wire format."""
    if len(data) < 4:
        return None
    ssid_len = data[0]
    if len(data) < 1 + ssid_len + 3:
        return None
    ssid = data[1 : 1 + ssid_len].decode("utf-8", errors="replace")
    offset = 1 + ssid_len
    rssi = struct.unpack_from("b", data, offset)[0]
    security = data[offset + 1]
    channel = data[offset + 2]
    return {
        "ssid": ssid,
        "rssi": rssi,
        "security": SECURITY_NAMES.get(security, f"Unknown({security})"),
        "channel": channel,
    }


def encode_credentials(ssid: str, psk: str, security: int) -> bytes:
    """Encode credentials to wire format."""
    ssid_bytes = ssid.encode("utf-8")[:32]
    psk_bytes = psk.encode("utf-8")[:64]
    return (
        bytes([len(ssid_bytes)])
        + ssid_bytes
        + bytes([len(psk_bytes)])
        + psk_bytes
        + bytes([security])
    )


def decode_status(data: bytes) -> dict:
    """Decode status from wire format."""
    if len(data) < 5:
        return None
    state = data[0]
    ip = f"{data[1]}.{data[2]}.{data[3]}.{data[4]}"
    return {
        "state": STATE_NAMES.get(state, f"Unknown({state})"),
        "ip": ip,
    }


async def cmd_discover(args):
    """Discover devices advertising the WiFi provisioning service."""
    print(f"Scanning for BLE devices ({args.timeout}s)...")
    devices = await BleakScanner.discover(
        timeout=args.timeout,
        service_uuids=[UUID_SVC],
    )
    if not devices:
        print("No WiFi provisioning devices found.")
        return
    print(f"\nFound {len(devices)} device(s):\n")
    for d in devices:
        print(f"  {d.name or 'Unknown'}")
        print(f"    Address: {d.address}")
        print(f"    RSSI:    {d.rssi} dBm")
        print()


async def cmd_scan_aps(args):
    """Trigger WiFi scan and display results."""
    results = []

    def on_scan_result(_, data: bytearray):
        result = decode_scan_result(bytes(data))
        if result:
            results.append(result)

    async with BleakClient(args.address) as client:
        print(f"Connected to {args.address}")
        await client.start_notify(UUID_SCAN_RES, on_scan_result)
        print("Triggering WiFi scan...")
        await client.write_gatt_char(UUID_SCAN_TRIG, b"\x01")
        await asyncio.sleep(args.timeout)
        await client.stop_notify(UUID_SCAN_RES)

    if not results:
        print("No APs found.")
        return

    print(f"\n{'SSID':<32} {'RSSI':>5} {'Ch':>3} {'Security'}")
    print("-" * 60)
    for r in sorted(results, key=lambda x: x["rssi"], reverse=True):
        print(f"{r['ssid']:<32} {r['rssi']:>5} {r['channel']:>3} {r['security']}")


async def cmd_provision(args):
    """Send WiFi credentials to device."""
    sec_map = {
        "open": 0,
        "wpa": 1,
        "wpa2": 2,
        "wpa2-sha256": 3,
        "wpa3": 4,
    }
    security = sec_map.get(args.security, 2)

    status_event = asyncio.Event()
    final_status = {}

    def on_status(_, data: bytearray):
        s = decode_status(bytes(data))
        if s:
            final_status.update(s)
            if s["state"] in ("CONNECTED", "IDLE"):
                status_event.set()

    async with BleakClient(args.address) as client:
        print(f"Connected to {args.address}")
        await client.start_notify(UUID_STATUS, on_status)

        cred = encode_credentials(args.ssid, args.psk, security)
        print(f"Sending credentials (SSID: {args.ssid}, security: {args.security})...")
        await client.write_gatt_char(UUID_CRED, cred)

        print("Waiting for connection result...")
        try:
            await asyncio.wait_for(status_event.wait(), timeout=args.timeout)
        except asyncio.TimeoutError:
            print("Timeout waiting for connection result.")

        await client.stop_notify(UUID_STATUS)

    if final_status:
        print(f"\nResult: {final_status['state']}")
        if final_status.get("ip") and final_status["ip"] != "0.0.0.0":
            print(f"IP:     {final_status['ip']}")


async def cmd_status(args):
    """Query device status."""
    async with BleakClient(args.address) as client:
        print(f"Connected to {args.address}")
        data = await client.read_gatt_char(UUID_STATUS)
        status = decode_status(bytes(data))
        if status:
            print(f"State: {status['state']}")
            print(f"IP:    {status['ip']}")
        else:
            print("Failed to decode status.")


async def cmd_factory_reset(args):
    """Trigger factory reset."""
    async with BleakClient(args.address) as client:
        print(f"Connected to {args.address}")
        print("Sending factory reset...")
        await client.write_gatt_char(UUID_RESET, b"\xff")
        print("Factory reset sent.")


def main():
    parser = argparse.ArgumentParser(
        description="WiFi provisioning over BLE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # discover
    p = sub.add_parser("discover", help="Find WiFi provisioning devices")
    p.add_argument("-t", "--timeout", type=float, default=5.0, help="Scan timeout (s)")

    # scan-aps
    p = sub.add_parser("scan-aps", help="Trigger WiFi AP scan")
    p.add_argument("address", help="BLE device address")
    p.add_argument(
        "-t", "--timeout", type=float, default=10.0, help="Wait time for results (s)"
    )

    # provision
    p = sub.add_parser("provision", help="Send WiFi credentials")
    p.add_argument("address", help="BLE device address")
    p.add_argument("ssid", help="WiFi SSID")
    p.add_argument("psk", help="WiFi password")
    p.add_argument(
        "-s",
        "--security",
        choices=["open", "wpa", "wpa2", "wpa2-sha256", "wpa3"],
        default="wpa2",
        help="Security type (default: wpa2)",
    )
    p.add_argument(
        "-t", "--timeout", type=float, default=30.0, help="Connection timeout (s)"
    )

    # status
    p = sub.add_parser("status", help="Query device status")
    p.add_argument("address", help="BLE device address")

    # factory-reset
    p = sub.add_parser("factory-reset", help="Factory reset device")
    p.add_argument("address", help="BLE device address")

    args = parser.parse_args()

    commands = {
        "discover": cmd_discover,
        "scan-aps": cmd_scan_aps,
        "provision": cmd_provision,
        "status": cmd_status,
        "factory-reset": cmd_factory_reset,
    }

    asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    main()
