#!/usr/bin/env python3
"""
Batch BLE throughput + PPK2 power measurement.

Runs N consecutive tests, saves all raw per-second data to JSON.
Supports resume from partial runs. After completion, use power.analysis to analyze.

Usage:
    python -m power.batch_test --ppk2-port /dev/tty.usbmodemXXXX
    python -m power.batch_test --ppk2-port /dev/tty.usbmodemXXXX --num-runs 5 --duration 60
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import time
import threading
import statistics
import json
import argparse
from typing import Optional

from bleak import BleakClient, BleakScanner

from ble.uuids import NUS_TX_CHAR_UUID
from power.ppk2_utils import (
    PPK2Config, init_ppk2, reset_ppk2_serial,
    collect_power_samples, build_power_buckets,
)


class PowerThroughputBatch:
    """Batch BLE throughput + PPK2 power measurement."""

    def __init__(
        self,
        device_name: str = "nRF54L15_Test",
        ppk2_port: str = "",
        voltage_mv: int = 4000,
        duration: int = 300,
        settle_time: int = 10,
        num_runs: int = 10,
        output_file: str = "power_throughput_raw.json",
        scan_timeout: float = 15.0,
    ):
        self.device_name = device_name
        self.ppk2_config = PPK2Config(port=ppk2_port, voltage_mv=voltage_mv)
        self.duration = duration
        self.settle_time = settle_time
        self.num_runs = num_runs
        self.output_file = output_file
        self.scan_timeout = scan_timeout
        self.ppk2 = None

    def _run_single_test(self, run_number: int) -> Optional[dict]:
        """Run a single throughput+power test. Returns dict of results."""
        state = {
            "rx_bytes": 0,
            "start_time": None,
            "measuring": False,
            "power_log": [],
            "power_lock": threading.Lock(),
            "throughput_log": [],
        }

        def notification_handler(sender, data):
            state["rx_bytes"] += len(data)

        def ppk2_measure_thread():
            while not state["measuring"]:
                time.sleep(0.1)
            time.sleep(self.settle_time)
            print(f"  PPK2: Starting measurement ({self.duration}s)...", flush=True)
            collect_power_samples(
                self.ppk2, self.duration, state["power_log"], state["power_lock"]
            )

        async def ble_test():
            # Power cycle DUT
            print(f"  Power cycling DUT...", flush=True)
            self.ppk2.toggle_DUT_power("OFF")
            await asyncio.sleep(2)
            self.ppk2.toggle_DUT_power("ON")
            await asyncio.sleep(4)

            print(f"  BLE: Scanning...", flush=True)
            device = await BleakScanner.find_device_by_name(
                self.device_name, timeout=self.scan_timeout
            )
            if device is None:
                print(f"  ERROR: Could not find '{self.device_name}'", flush=True)
                return False

            print(f"  BLE: Connecting...", flush=True)

            measure_t = threading.Thread(target=ppk2_measure_thread, daemon=True)
            measure_t.start()

            async with BleakClient(device) as client:
                mtu = client.mtu_size
                print(f"  BLE: Connected, MTU={mtu}", flush=True)
                await client.start_notify(NUS_TX_CHAR_UUID, notification_handler)

                state["start_time"] = time.time()
                state["measuring"] = True

                total_time = self.settle_time + self.duration + 2
                prev_bytes = 0
                for i in range(total_time):
                    await asyncio.sleep(1.0)
                    now = time.time()
                    delta = state["rx_bytes"] - prev_bytes
                    prev_bytes = state["rx_bytes"]
                    instant_kbps = (delta * 8) / 1000
                    elapsed = now - state["start_time"]
                    avg_kbps = (state["rx_bytes"] * 8) / 1000 / elapsed

                    state["throughput_log"].append({
                        "timestamp": now,
                        "elapsed_s": round(elapsed, 1),
                        "instant_kbps": round(instant_kbps, 1),
                        "avg_kbps": round(avg_kbps, 1),
                        "total_bytes": state["rx_bytes"],
                    })

                    if i % 30 == 0:
                        with state["power_lock"]:
                            if state["power_log"]:
                                latest = state["power_log"][-1][1]
                                pwr = (f", power: {statistics.mean(latest)/1000:.2f} mA"
                                       if latest else "")
                            else:
                                pwr = ""
                        print(f"  [{i:3d}s] {instant_kbps:.0f} kbps (inst) "
                              f"{avg_kbps:.0f} kbps (avg){pwr}", flush=True)

            measure_t.join(timeout=10)
            return True

        success = asyncio.run(ble_test())
        if not success:
            return None

        power_seconds = build_power_buckets(state["power_log"], state["power_lock"])
        elapsed = time.time() - state["start_time"]
        avg_throughput = (state["rx_bytes"] * 8) / 1000 / elapsed

        return {
            "run_number": run_number,
            "start_time_iso": time.strftime(
                "%Y-%m-%dT%H:%M:%S", time.localtime(state["start_time"])
            ),
            "duration_s": round(elapsed, 1),
            "total_bytes": state["rx_bytes"],
            "avg_throughput_kbps": round(avg_throughput, 1),
            "ppk2_voltage_mV": self.ppk2_config.voltage_mv,
            "throughput_per_second": state["throughput_log"],
            "power_per_second": power_seconds,
        }

    def run(self) -> dict:
        """Run all batch tests. Returns the full results dict."""
        print(f"=== Batch Power+Throughput Test ===", flush=True)
        print(f"Runs: {self.num_runs}, Duration: {self.duration}s each", flush=True)
        print(f"Output: {self.output_file}", flush=True)
        print(flush=True)

        # Initialize PPK2
        reset_ppk2_serial(self.ppk2_config.port)
        self.ppk2 = init_ppk2(self.ppk2_config)

        # Resume from existing data if available
        try:
            with open(self.output_file) as f:
                all_results = json.load(f)
            existing_runs = len(all_results["runs"])
            print(f"Resuming: found {existing_runs} existing runs", flush=True)
        except (FileNotFoundError, json.JSONDecodeError):
            all_results = {
                "config": {
                    "device_name": self.device_name,
                    "ppk2_voltage_mV": self.ppk2_config.voltage_mv,
                    "measure_duration_s": self.duration,
                    "settle_time_s": self.settle_time,
                    "num_runs": self.num_runs,
                    "test_date": time.strftime("%Y-%m-%d"),
                },
                "runs": [],
            }
            existing_runs = 0

        start_run = existing_runs + 1
        for run in range(start_run, self.num_runs + 1):
            print(f"\n{'='*60}", flush=True)
            print(f"RUN {run}/{self.num_runs}", flush=True)
            print(f"{'='*60}", flush=True)

            try:
                result = self._run_single_test(run)
            except Exception as e:
                print(f"  Run {run} EXCEPTION: {e}", flush=True)
                result = None

            if result is None:
                print(f"  Run {run} FAILED, retrying in 10s...", flush=True)
                time.sleep(10)
                try:
                    result = self._run_single_test(run)
                except Exception as e:
                    print(f"  Run {run} retry EXCEPTION: {e}", flush=True)
                    result = None

            if result:
                all_results["runs"].append(result)
                power_data = result["power_per_second"]
                if power_data:
                    avg_mA = statistics.mean([p["avg_uA"] for p in power_data]) / 1000
                    peak_mA = max([p["peak_uA"] for p in power_data]) / 1000
                    print(f"  Result: {result['avg_throughput_kbps']:.1f} kbps, "
                          f"{avg_mA:.2f} mA avg, {peak_mA:.2f} mA peak", flush=True)

                with open(self.output_file, "w") as f:
                    json.dump(all_results, f, indent=2)
                print(f"  Saved to {self.output_file}", flush=True)
            else:
                print(f"  Run {run} FAILED twice, skipping", flush=True)

        print(f"\n{'='*60}", flush=True)
        print(f"ALL DONE - {len(all_results['runs'])} runs completed", flush=True)
        print(f"Data saved to {self.output_file}", flush=True)
        print(f"Run: python -m power.analysis --input {self.output_file}", flush=True)
        print(f"{'='*60}", flush=True)

        return all_results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch BLE Throughput + PPK2 Power Measurement"
    )
    parser.add_argument("--name", default="nRF54L15_Test",
                        help="Device name to scan for (default: nRF54L15_Test)")
    parser.add_argument("--ppk2-port", required=True,
                        help="PPK2 serial port (e.g., /dev/tty.usbmodemXXXX)")
    parser.add_argument("--voltage", type=int, default=4000,
                        help="PPK2 source voltage in mV (default: 4000)")
    parser.add_argument("--duration", type=int, default=300,
                        help="Measurement duration per run in seconds (default: 300)")
    parser.add_argument("--settle-time", type=int, default=10,
                        help="Settle time before measurement in seconds (default: 10)")
    parser.add_argument("--num-runs", type=int, default=10,
                        help="Number of test runs (default: 10)")
    parser.add_argument("--output", default="power_throughput_raw.json",
                        help="Output JSON file (default: power_throughput_raw.json)")
    parser.add_argument("--scan-timeout", type=float, default=15.0,
                        help="BLE scan timeout in seconds (default: 15)")
    return parser


def main():
    args = build_parser().parse_args()

    batch = PowerThroughputBatch(
        device_name=args.name,
        ppk2_port=args.ppk2_port,
        voltage_mv=args.voltage,
        duration=args.duration,
        settle_time=args.settle_time,
        num_runs=args.num_runs,
        output_file=args.output,
        scan_timeout=args.scan_timeout,
    )

    try:
        batch.run()
    except KeyboardInterrupt:
        print("\nStopped by user")


if __name__ == "__main__":
    main()
