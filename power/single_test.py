#!/usr/bin/env python3
"""
Combined BLE throughput + PPK2 power measurement (single run).

Runs GATT notification throughput test while simultaneously measuring power
consumption via Nordic PPK2. Reports per-second power profile and efficiency.

Usage:
    python -m power.single_test --ppk2-port /dev/tty.usbmodemXXXX
    python -m power.single_test --ppk2-port /dev/tty.usbmodemXXXX --duration 60
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import time
import threading
import statistics
import argparse
from typing import Optional

from bleak import BleakClient, BleakScanner

from ble.uuids import NUS_TX_CHAR_UUID
from power.ppk2_utils import PPK2Config, init_ppk2, collect_power_samples, build_power_buckets


class PowerThroughputTest:
    """Single-run BLE throughput + PPK2 power measurement."""

    def __init__(
        self,
        device_name: str = "nRF54L15_Test",
        ppk2_port: str = "",
        voltage_mv: int = 4000,
        duration: int = 30,
        settle_time: int = 5,
        boot_wait: int = 4,
        scan_timeout: float = 10.0,
    ):
        self.device_name = device_name
        self.ppk2_config = PPK2Config(port=ppk2_port, voltage_mv=voltage_mv)
        self.duration = duration
        self.settle_time = settle_time
        self.boot_wait = boot_wait
        self.scan_timeout = scan_timeout

        self.rx_bytes = 0
        self.start_time: Optional[float] = None
        self.measuring = False
        self.power_log = []
        self.power_lock = threading.Lock()
        self.ppk2 = None

    def _notification_handler(self, sender, data):
        self.rx_bytes += len(data)

    def _ppk2_measure_thread(self):
        """Collect power samples after settle time."""
        while not self.measuring:
            time.sleep(0.1)
        time.sleep(self.settle_time)
        print("PPK2: Starting power measurement...", flush=True)
        collect_power_samples(self.ppk2, self.duration, self.power_log, self.power_lock)

    async def run(self) -> dict:
        """Run the combined test. Returns structured results."""
        # Step 1: Power up device via PPK2
        print("PPK2: Initializing...", flush=True)
        self.ppk2 = init_ppk2(self.ppk2_config)

        # Step 2: Wait for device boot
        print(f"Waiting {self.boot_wait}s for device to boot...", flush=True)
        await asyncio.sleep(self.boot_wait)

        # Step 3: BLE scan
        print(f"BLE: Scanning for {self.device_name}...", flush=True)
        device = await BleakScanner.find_device_by_name(
            self.device_name, timeout=self.scan_timeout
        )
        if device is None:
            print(f"ERROR: Could not find '{self.device_name}'")
            return {"error": f"device '{self.device_name}' not found"}

        print(f"BLE: Found {device.name}, connecting...", flush=True)

        # Step 4: Start measurement thread
        measure_t = threading.Thread(target=self._ppk2_measure_thread, daemon=True)
        measure_t.start()

        async with BleakClient(device) as client:
            print(f"BLE: Connected, MTU={client.mtu_size}", flush=True)
            await client.start_notify(NUS_TX_CHAR_UUID, self._notification_handler)
            print("BLE: Notifications enabled", flush=True)

            self.start_time = time.time()
            self.measuring = True

            total_time = self.settle_time + self.duration + 2
            prev_bytes = 0
            for i in range(total_time):
                await asyncio.sleep(1.0)
                now = time.time()
                delta = self.rx_bytes - prev_bytes
                prev_bytes = self.rx_bytes
                instant_kbps = (delta * 8) / 1000
                avg_kbps = (self.rx_bytes * 8) / 1000 / (now - self.start_time)

                with self.power_lock:
                    if self.power_log:
                        latest = self.power_log[-1][1]
                        recent_avg_uA = statistics.mean(latest) if latest else 0
                        recent_peak_uA = max(latest) if latest else 0
                    else:
                        recent_avg_uA = 0
                        recent_peak_uA = 0

                ts_str = time.strftime("%H:%M:%S", time.localtime(now))
                power_str = (f"  power: avg={recent_avg_uA/1000:.2f} mA, "
                             f"peak={recent_peak_uA/1000:.2f} mA") if recent_avg_uA > 0 else ""
                print(f"  [{ts_str}] {instant_kbps:6.0f} kbps (inst) "
                      f"{avg_kbps:6.0f} kbps (avg){power_str}", flush=True)

        measure_t.join(timeout=5)
        return self._build_results()

    def _build_results(self) -> dict:
        """Build structured results dict."""
        all_samples = []
        with self.power_lock:
            for ts, samples in self.power_log:
                all_samples.extend([s for s in samples if 0 < s < 100000])

        elapsed = time.time() - self.start_time
        avg_throughput = (self.rx_bytes * 8) / 1000 / elapsed
        voltage_mv = self.ppk2_config.voltage_mv

        result = {
            "duration_s": round(elapsed, 1),
            "total_bytes": self.rx_bytes,
            "avg_throughput_kbps": round(avg_throughput, 1),
            "voltage_mv": voltage_mv,
            "power_per_second": build_power_buckets(self.power_log, self.power_lock),
        }

        if all_samples:
            avg_uA = statistics.mean(all_samples)
            avg_mA = avg_uA / 1000
            peak_uA = max(all_samples)
            peak_mA = peak_uA / 1000
            avg_mW = avg_mA * voltage_mv / 1000
            bits_per_sec = avg_throughput * 1000
            nJ_per_bit = (avg_mW * 1e6) / bits_per_sec if bits_per_sec > 0 else 0

            result.update({
                "avg_current_uA": round(avg_uA, 1),
                "peak_current_uA": round(peak_uA, 1),
                "avg_power_mW": round(avg_mW, 3),
                "energy_per_bit_nJ": round(nJ_per_bit, 1),
                "power_sample_count": len(all_samples),
            })

        return result

    def report(self, result: dict):
        """Print human-readable report."""
        power_seconds = result.get("power_per_second", [])

        # Per-second power profile
        if power_seconds:
            print("\n" + "=" * 70, flush=True)
            print("PER-SECOND POWER PROFILE", flush=True)
            print("=" * 70, flush=True)
            print(f"{'Time':>10s}  {'Avg (mA)':>10s}  {'Peak (mA)':>10s}  "
                  f"{'Min (mA)':>10s}  {'Samples':>8s}", flush=True)
            print("-" * 70, flush=True)
            for p in power_seconds:
                abs_time = time.strftime("%H:%M:%S", time.localtime(p["timestamp"]))
                print(f"{abs_time:>10s}  {p['avg_uA']/1000:10.3f}  "
                      f"{p['peak_uA']/1000:10.3f}  {p['min_uA']/1000:10.3f}  "
                      f"{p['sample_count']:8d}", flush=True)

        # Summary
        print("\n" + "=" * 70, flush=True)
        print("SUMMARY", flush=True)
        print("=" * 70, flush=True)

        print(f"\n--- Throughput ---", flush=True)
        print(f"Duration:       {result['duration_s']:.1f} s", flush=True)
        print(f"Total RX:       {result['total_bytes']:,} bytes", flush=True)
        print(f"Avg throughput: {result['avg_throughput_kbps']:.1f} kbps", flush=True)

        if "avg_current_uA" in result:
            avg_mA = result["avg_current_uA"] / 1000
            peak_mA = result["peak_current_uA"] / 1000
            print(f"\n--- Power ({result['power_sample_count']:,} samples) ---", flush=True)
            print(f"Average:    {result['avg_current_uA']:.1f} uA  ({avg_mA:.3f} mA)", flush=True)
            print(f"Peak:       {result['peak_current_uA']:.1f} uA  ({peak_mA:.3f} mA)", flush=True)
            print(f"Avg power:  {result['avg_power_mW']:.3f} mW @ {result['voltage_mv']} mV", flush=True)
            if result.get("energy_per_bit_nJ", 0) > 0:
                print(f"\n--- Efficiency ---", flush=True)
                print(f"Energy/bit:  {result['energy_per_bit_nJ']:.1f} nJ/bit", flush=True)
                print(f"Energy/byte: {result['energy_per_bit_nJ']*8:.1f} nJ/byte", flush=True)
        else:
            print("\nNo valid power data collected", flush=True)

        print("=" * 70, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BLE Throughput + PPK2 Power Measurement (single run)"
    )
    parser.add_argument("--name", default="nRF54L15_Test",
                        help="Device name to scan for (default: nRF54L15_Test)")
    parser.add_argument("--ppk2-port", required=True,
                        help="PPK2 serial port (e.g., /dev/tty.usbmodemXXXX)")
    parser.add_argument("--voltage", type=int, default=4000,
                        help="PPK2 source voltage in mV (default: 4000)")
    parser.add_argument("--duration", type=int, default=30,
                        help="Measurement duration in seconds (default: 30)")
    parser.add_argument("--settle-time", type=int, default=5,
                        help="Settle time before measurement in seconds (default: 5)")
    parser.add_argument("--boot-wait", type=int, default=4,
                        help="Wait time for device boot in seconds (default: 4)")
    parser.add_argument("--scan-timeout", type=float, default=10.0,
                        help="BLE scan timeout in seconds (default: 10)")
    return parser


def main():
    args = build_parser().parse_args()

    test = PowerThroughputTest(
        device_name=args.name,
        ppk2_port=args.ppk2_port,
        voltage_mv=args.voltage,
        duration=args.duration,
        settle_time=args.settle_time,
        boot_wait=args.boot_wait,
        scan_timeout=args.scan_timeout,
    )

    try:
        result = asyncio.run(test.run())
        if "error" not in result:
            test.report(result)
    except KeyboardInterrupt:
        print("\nStopped by user")


if __name__ == "__main__":
    main()
