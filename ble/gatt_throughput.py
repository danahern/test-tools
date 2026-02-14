#!/usr/bin/env python3
"""
BLE GATT Throughput Testing Tool

Tests data transfer rates with Zephyr BLE devices using Nordic UART Service (NUS).
Supports TX, echo (round-trip latency), and burst transfer tests.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import argparse
import time
import statistics
from dataclasses import dataclass, field
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

from ble.uuids import NUS_SERVICE_UUID, NUS_RX_CHAR_UUID, NUS_TX_CHAR_UUID


@dataclass
class ThroughputStats:
    """Collects and reports throughput statistics."""
    bytes_sent: int = 0
    bytes_received: int = 0
    packets_sent: int = 0
    packets_received: int = 0
    start_time: float = 0.0
    latencies: list = field(default_factory=list)

    def start(self):
        self.start_time = time.time()

    def elapsed(self) -> float:
        return time.time() - self.start_time

    def tx_throughput(self) -> float:
        """Returns TX throughput in bytes/sec."""
        elapsed = self.elapsed()
        return self.bytes_sent / elapsed if elapsed > 0 else 0

    def rx_throughput(self) -> float:
        """Returns RX throughput in bytes/sec."""
        elapsed = self.elapsed()
        return self.bytes_received / elapsed if elapsed > 0 else 0

    def avg_latency(self) -> float:
        """Returns average round-trip latency in ms."""
        return statistics.mean(self.latencies) * 1000 if self.latencies else 0

    def to_dict(self) -> dict:
        """Return structured results."""
        elapsed = self.elapsed()
        result = {
            "duration_s": round(elapsed, 2),
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "tx_throughput_bps": round(self.tx_throughput(), 2),
            "rx_throughput_bps": round(self.rx_throughput(), 2),
            "tx_throughput_kbps": round(self.tx_throughput() * 8 / 1000, 2),
            "rx_throughput_kbps": round(self.rx_throughput() * 8 / 1000, 2),
        }
        if self.latencies:
            result["avg_latency_ms"] = round(self.avg_latency(), 2)
            result["min_latency_ms"] = round(min(self.latencies) * 1000, 2)
            result["max_latency_ms"] = round(max(self.latencies) * 1000, 2)
        return result

    def report(self):
        elapsed = self.elapsed()
        print("\n" + "=" * 50)
        print("THROUGHPUT TEST RESULTS")
        print("=" * 50)
        print(f"Duration:        {elapsed:.2f} sec")
        print(f"Packets sent:    {self.packets_sent}")
        print(f"Packets recv:    {self.packets_received}")
        print(f"Bytes sent:      {self.bytes_sent:,}")
        print(f"Bytes received:  {self.bytes_received:,}")
        print(f"TX throughput:   {self.tx_throughput():.2f} B/s ({self.tx_throughput() * 8 / 1000:.2f} kbit/s)")
        print(f"RX throughput:   {self.rx_throughput():.2f} B/s ({self.rx_throughput() * 8 / 1000:.2f} kbit/s)")
        if self.latencies:
            print(f"Avg latency:     {self.avg_latency():.2f} ms")
            print(f"Min latency:     {min(self.latencies) * 1000:.2f} ms")
            print(f"Max latency:     {max(self.latencies) * 1000:.2f} ms")
        print("=" * 50)


class BLEThroughputTester:
    """Tests BLE throughput using Nordic UART Service."""

    def __init__(self, device_name: Optional[str] = None, device_addr: Optional[str] = None):
        self.device_name = device_name
        self.device_addr = device_addr
        self.client: Optional[BleakClient] = None
        self.stats = ThroughputStats()
        self._rx_event = asyncio.Event()
        self._last_rx_data: bytes = b""
        self._pending_echo: Optional[float] = None

    async def scan(self, timeout: float = 10.0) -> list:
        """Scan for BLE devices with NUS service."""
        print(f"Scanning for BLE devices ({timeout}s)...")
        devices = await BleakScanner.discover(timeout=timeout)

        nus_devices = []
        for d in devices:
            if d.name and ("NUS" in d.name.upper() or
                          "BLE" in d.name.upper() or
                          "DATA" in d.name.upper() or
                          "BRIDGE" in d.name.upper()):
                nus_devices.append(d)
                print(f"  Found: {d.name} ({d.address})")

        if not nus_devices:
            print("  No matching devices found. Showing all devices:")
            for d in devices:
                if d.name:
                    print(f"    {d.name} ({d.address})")

        return nus_devices

    async def connect(self) -> bool:
        """Connect to the target device."""
        device = None

        if self.device_addr:
            print(f"Connecting to {self.device_addr}...")
            device = self.device_addr
        elif self.device_name:
            print(f"Scanning for '{self.device_name}'...")
            device = await BleakScanner.find_device_by_name(self.device_name, timeout=10.0)
            if not device:
                print(f"Device '{self.device_name}' not found")
                return False
        else:
            devices = await self.scan()
            if devices:
                device = devices[0]
                print(f"Using first found device: {device.name}")
            else:
                print("No devices found")
                return False

        self.client = BleakClient(device)
        await self.client.connect()
        print(f"Connected: {self.client.is_connected}")

        await self.client.start_notify(NUS_TX_CHAR_UUID, self._on_notify)
        print("Subscribed to NUS TX notifications")

        return True

    async def disconnect(self):
        """Disconnect from device."""
        if self.client and self.client.is_connected:
            await self.client.stop_notify(NUS_TX_CHAR_UUID)
            await self.client.disconnect()
            print("Disconnected")

    def _on_notify(self, sender: BleakGATTCharacteristic, data: bytearray):
        """Handle incoming notifications."""
        self.stats.bytes_received += len(data)
        self.stats.packets_received += 1
        self._last_rx_data = bytes(data)

        if self._pending_echo is not None:
            latency = time.time() - self._pending_echo
            self.stats.latencies.append(latency)
            self._pending_echo = None

        self._rx_event.set()

    async def send(self, data: bytes) -> int:
        """Send data to device via NUS RX characteristic."""
        if not self.client or not self.client.is_connected:
            return 0

        await self.client.write_gatt_char(NUS_RX_CHAR_UUID, data)
        self.stats.bytes_sent += len(data)
        self.stats.packets_sent += 1
        return len(data)

    async def run_tx_test(self, duration: float = 10.0, packet_size: int = 20):
        """Run transmit-only throughput test."""
        print(f"\nRunning TX test: {duration}s, {packet_size} byte packets")

        data = bytes([i % 256 for i in range(packet_size)])

        self.stats = ThroughputStats()
        self.stats.start()

        while self.stats.elapsed() < duration:
            await self.send(data)
            await asyncio.sleep(0.001)

        self.stats.report()

    async def run_echo_test(self, duration: float = 10.0, packet_size: int = 20):
        """Run echo (round-trip) latency test."""
        print(f"\nRunning echo test: {duration}s, {packet_size} byte packets")

        data = bytes([i % 256 for i in range(packet_size)])

        self.stats = ThroughputStats()
        self.stats.start()

        while self.stats.elapsed() < duration:
            self._rx_event.clear()
            self._pending_echo = time.time()

            await self.send(data)

            try:
                await asyncio.wait_for(self._rx_event.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                print("  Echo timeout")
                self._pending_echo = None

            await asyncio.sleep(0.01)

        self.stats.report()

    async def run_burst_test(self, num_packets: int = 100, packet_size: int = 20):
        """Run burst transfer test."""
        print(f"\nRunning burst test: {num_packets} packets, {packet_size} bytes each")

        data = bytes([i % 256 for i in range(packet_size)])

        self.stats = ThroughputStats()
        self.stats.start()

        for i in range(num_packets):
            await self.send(data)
            if (i + 1) % 10 == 0:
                print(f"  Sent {i + 1}/{num_packets} packets")
                await asyncio.sleep(0.01)

        # Wait for any pending responses
        await asyncio.sleep(1.0)

        self.stats.report()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BLE GATT Throughput Testing Tool")
    parser.add_argument("--scan", action="store_true", help="Scan for devices only")
    parser.add_argument("--name", type=str, help="Device name to connect to")
    parser.add_argument("--addr", type=str, help="Device address to connect to")
    parser.add_argument("--test", choices=["tx", "echo", "burst", "all"],
                        default="all", help="Test type to run")
    parser.add_argument("--duration", type=float, default=10.0,
                        help="Test duration in seconds")
    parser.add_argument("--size", type=int, default=20,
                        help="Packet size in bytes (max ~240 for BLE)")
    parser.add_argument("--packets", type=int, default=100,
                        help="Number of packets for burst test")
    return parser


async def main():
    args = build_parser().parse_args()

    tester = BLEThroughputTester(device_name=args.name, device_addr=args.addr)

    if args.scan:
        await tester.scan()
        return

    try:
        if not await tester.connect():
            return

        if args.test in ("tx", "all"):
            await tester.run_tx_test(args.duration, args.size)

        if args.test in ("echo", "all"):
            await tester.run_echo_test(args.duration, args.size)

        if args.test in ("burst", "all"):
            await tester.run_burst_test(args.packets, args.size)

    finally:
        await tester.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
