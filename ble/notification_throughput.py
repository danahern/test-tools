#!/usr/bin/env python3
"""
BLE Notification Throughput Test

Tests bidirectional BLE throughput with independent TX rate control for both
host and device. Supports configuring RISC-V workloads on dual-core firmware.

Usage:
    python -m ble.notification_throughput
    python -m ble.notification_throughput --mac-tx 100 --device-tx 50
    python -m ble.notification_throughput --name nRF54L15_Dual --workload 6
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import time
import argparse
from typing import Optional

from bleak import BleakClient, BleakScanner

from ble.uuids import NUS_TX_CHAR_UUID, NUS_RX_CHAR_UUID, NUS_CTRL_CHAR_UUID, RISCV_WORKLOAD_UUID

WORKLOAD_NAMES = {
    0: "Idle",
    1: "Matrix Multiplication",
    2: "Sorting",
    3: "FFT Simulation",
    4: "Crypto Simulation",
    5: "Mixed",
    6: "Audio Pipeline (3 mics, beamforming, VAD)",
    7: "Audio Pipeline + AEC (3 mics, beamforming, VAD, echo cancellation)",
    8: "Proximity-Based VAD (near-field detection)",
    9: "Chest Resonance Detection (50-200 Hz)",
    10: "Clothing Rustle Suppression (impulse noise)",
    11: "Spatial Noise Cancellation (GSC + adaptive filter)",
    12: "Wind Noise Reduction (correlation-based)",
    13: "Full Necklace Pipeline (6-stage processing)",
}


class NotificationThroughputTester:
    """Bidirectional BLE throughput tester with rate control."""

    def __init__(
        self,
        device_name: str = "nRF54L15_Test",
        mac_tx_kbps: Optional[int] = None,
        device_tx_kbps: Optional[int] = None,
        workload: Optional[int] = None,
        packet_size: int = 495,
        scan_timeout: float = 10.0,
    ):
        self.device_name = device_name
        self.mac_tx_kbps = mac_tx_kbps
        self.device_tx_kbps = device_tx_kbps
        self.workload = workload
        self.packet_size = packet_size
        self.scan_timeout = scan_timeout

        self.rx_bytes = 0
        self.tx_bytes = 0
        self.start_time: Optional[float] = None

    def _notification_handler(self, sender, data):
        """Handle notifications from device."""
        self.rx_bytes += len(data)

    async def _print_stats(self):
        """Print throughput statistics every second."""
        while True:
            await asyncio.sleep(1.0)
            if self.start_time is None:
                continue
            elapsed = time.time() - self.start_time
            rx_kbps = (self.rx_bytes * 8) / 1000 / elapsed
            tx_kbps = (self.tx_bytes * 8) / 1000 / elapsed
            print(f"\n=== Throughput Stats (avg over {elapsed:.1f}s) ===")
            print(f"RX (from device): {self.rx_bytes:,} bytes ({rx_kbps:.1f} kbps)")
            print(f"TX (to device):   {self.tx_bytes:,} bytes ({tx_kbps:.1f} kbps)")
            print(f"Total:            {self.rx_bytes + self.tx_bytes:,} bytes")
            print("=" * 50)

    async def _send_data(self, client):
        """Continuously send data to device."""
        if self.mac_tx_kbps == 0:
            print("TX DISABLED - RX only mode (not sending data)")
            self.start_time = time.time()
            while True:
                await asyncio.sleep(1)
            return

        packet = bytes([i % 256 for i in range(self.packet_size)])

        if self.mac_tx_kbps is None:
            delay = 0.01
            print("Starting continuous data transmission (MAX SPEED)...")
        else:
            bytes_per_sec = (self.mac_tx_kbps * 1000) / 8
            delay = self.packet_size / bytes_per_sec
            print(f"Starting continuous data transmission (TARGET: {self.mac_tx_kbps} kbps)...")
            print(f"Sending {self.packet_size} byte packets every {delay*1000:.1f} ms")

        self.start_time = time.time()

        while True:
            try:
                await client.write_gatt_char(NUS_RX_CHAR_UUID, packet, response=False)
                self.tx_bytes += len(packet)
                await asyncio.sleep(delay)
            except Exception as e:
                print(f"Error sending data: {e}")
                await asyncio.sleep(0.1)

    def to_dict(self) -> dict:
        """Return structured results."""
        if self.start_time is None:
            return {"error": "test not started"}
        elapsed = time.time() - self.start_time
        return {
            "duration_s": round(elapsed, 1),
            "rx_bytes": self.rx_bytes,
            "tx_bytes": self.tx_bytes,
            "rx_kbps": round((self.rx_bytes * 8) / 1000 / elapsed, 1) if elapsed > 0 else 0,
            "tx_kbps": round((self.tx_bytes * 8) / 1000 / elapsed, 1) if elapsed > 0 else 0,
            "device_name": self.device_name,
            "mac_tx_kbps": self.mac_tx_kbps,
            "device_tx_kbps": self.device_tx_kbps,
            "workload": self.workload,
        }

    async def run(self):
        """Connect and run the throughput test."""
        print(f"Scanning for {self.device_name}...")
        device = await BleakScanner.find_device_by_name(
            self.device_name, timeout=self.scan_timeout
        )
        if device is None:
            print(f"ERROR: Could not find device '{self.device_name}'")
            return

        print(f"Found device: {device.name} ({device.address})")
        print("Connecting...")

        async with BleakClient(device) as client:
            print(f"Connected: {client.is_connected}")

            try:
                mtu = client.mtu_size
                print(f"Negotiated MTU: {mtu} bytes (max payload: {mtu-3} bytes)")
            except Exception:
                print("MTU information not available")

            print("Enabling notifications...")
            await client.start_notify(NUS_TX_CHAR_UUID, self._notification_handler)
            print("Notifications enabled")

            await asyncio.sleep(1.5)

            # Configure device TX rate
            if self.device_tx_kbps is not None:
                print(f"Configuring device TX rate to {self.device_tx_kbps} kbps...")
                rate_bytes = self.device_tx_kbps.to_bytes(4, byteorder='little')
                await client.write_gatt_char(NUS_CTRL_CHAR_UUID, rate_bytes, response=False)
                await asyncio.sleep(0.5)
            else:
                print("Device TX rate: MAX SPEED (default)")

            # Configure RISC-V workload
            if self.workload is not None:
                workload_name = WORKLOAD_NAMES.get(self.workload, "Unknown")
                print(f"Configuring RISC-V workload to {self.workload} ({workload_name})...")
                await client.write_gatt_char(
                    RISCV_WORKLOAD_UUID, bytes([self.workload]), response=False
                )
                await asyncio.sleep(0.5)
                print(f"RISC-V workload set to: {workload_name}")

            stats_task = asyncio.create_task(self._print_stats())

            try:
                await self._send_data(client)
            except KeyboardInterrupt:
                print("\n\nTest stopped by user")
            finally:
                stats_task.cancel()
                if self.start_time:
                    elapsed = time.time() - self.start_time
                    print(f"\n=== Final Stats ===")
                    print(f"Test duration: {elapsed:.1f} seconds")
                    print(f"RX total: {self.rx_bytes:,} bytes ({(self.rx_bytes * 8 / 1000 / elapsed):.1f} kbps)")
                    print(f"TX total: {self.tx_bytes:,} bytes ({(self.tx_bytes * 8 / 1000 / elapsed):.1f} kbps)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='BLE Notification Throughput Test',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s                                    Max speed bidirectional
  %(prog)s --mac-tx 100                       Mac TX: 100 kbps, Device: max speed
  %(prog)s --device-tx 50                     Mac TX: max, Device TX: 50 kbps
  %(prog)s --mac-tx 0 --device-tx 50          Mac RX only, Device: 50 kbps
  %(prog)s --name nRF54L15_Dual --workload 6  Audio pipeline workload
        '''
    )
    parser.add_argument('--mac-tx', type=int, metavar='KBPS',
                        help='Mac to device TX rate in kbps (0=disabled, omit=max speed)')
    parser.add_argument('--device-tx', type=int, metavar='KBPS',
                        help='Device to Mac TX rate in kbps (0=disabled, omit=max speed)')
    parser.add_argument('--name', type=str, default='nRF54L15_Test',
                        help='Device name to scan for (default: nRF54L15_Test)')
    parser.add_argument('--workload', type=int, metavar='0-13', choices=range(0, 14),
                        help='RISC-V workload (0=Idle, 1=Matrix, 2=Sort, 3=FFT, 4=Crypto, '
                             '5=Mixed, 6=Audio, 7=Audio+AEC, 8-13=Necklace algos)')
    parser.add_argument('--packet-size', type=int, default=495,
                        help='Packet size in bytes (default: 495)')
    parser.add_argument('--scan-timeout', type=float, default=10.0,
                        help='Scan timeout in seconds (default: 10)')
    return parser


def main():
    args = build_parser().parse_args()

    if args.mac_tx is not None and args.mac_tx < 0:
        print("Error: Mac TX rate must be 0 or positive")
        sys.exit(1)
    if args.device_tx is not None and args.device_tx < 0:
        print("Error: Device TX rate must be 0 or positive")
        sys.exit(1)

    tester = NotificationThroughputTester(
        device_name=args.name,
        mac_tx_kbps=args.mac_tx,
        device_tx_kbps=args.device_tx,
        workload=args.workload,
        packet_size=args.packet_size,
        scan_timeout=args.scan_timeout,
    )

    try:
        asyncio.run(tester.run())
    except KeyboardInterrupt:
        print("\nExiting...")


if __name__ == "__main__":
    main()
