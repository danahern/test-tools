"""Shared PPK2 utilities for power measurement tools."""

import time
import statistics
from dataclasses import dataclass

try:
    from ppk2_api.ppk2_api import PPK2_API
except ImportError:
    PPK2_API = None


@dataclass
class PPK2Config:
    port: str
    voltage_mv: int = 4000


def check_ppk2_available():
    """Exit with install instructions if ppk2_api is not available."""
    if PPK2_API is None:
        print("Error: ppk2_api not installed")
        print("Install with: pip install ppk2-api")
        raise SystemExit(1)


def init_ppk2(config: PPK2Config) -> "PPK2_API":
    """Initialize PPK2 in source meter mode."""
    check_ppk2_available()
    ppk2 = PPK2_API(config.port)
    ppk2.get_modifiers()
    ppk2.use_source_meter()
    ppk2.set_source_voltage(config.voltage_mv)
    ppk2.toggle_DUT_power("ON")
    print(f"PPK2: Source mode at {config.voltage_mv} mV, DUT power ON", flush=True)
    return ppk2


def reset_ppk2_serial(port: str):
    """Stop any previous PPK2 streaming and flush stale data."""
    import serial
    ser = serial.Serial(port, 9600, timeout=0.1)
    ser.write(bytes([0x07]))  # PPK2 stop command
    time.sleep(0.5)
    while ser.in_waiting:
        ser.read(ser.in_waiting)
        time.sleep(0.1)
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    ser.close()
    time.sleep(2)


def collect_power_samples(ppk2, duration, power_log, power_lock):
    """Thread worker: collect power samples from PPK2 for `duration` seconds."""
    ppk2.start_measuring()
    measure_start = time.time()
    total_samples = 0

    while time.time() - measure_start < duration:
        read_data = ppk2.get_data()
        if read_data is not None:
            samples, _ = ppk2.get_samples(read_data)
            ts = time.time()
            with power_lock:
                power_log.append((ts, samples))
            total_samples += len(samples)
        time.sleep(0.01)

    ppk2.stop_measuring()
    elapsed = time.time() - measure_start
    print(f"PPK2: {total_samples:,} samples over {elapsed:.1f}s "
          f"({total_samples/elapsed:.0f} S/s)", flush=True)


def build_power_buckets(power_log, power_lock, sample_filter=200000):
    """Aggregate power samples into per-second buckets.

    Returns list of dicts with per-second power stats, or empty list.
    """
    buckets_out = []
    with power_lock:
        if not power_log:
            return buckets_out
        first_ts = power_log[0][0]
        buckets = {}
        for ts, samples in power_log:
            sec = int(ts - first_ts)
            if sec not in buckets:
                buckets[sec] = []
            buckets[sec].extend([s for s in samples if 0 < s < sample_filter])

        for sec in sorted(buckets.keys()):
            b = buckets[sec]
            if b:
                buckets_out.append({
                    "timestamp": first_ts + sec,
                    "elapsed_s": sec,
                    "avg_uA": round(statistics.mean(b), 1),
                    "median_uA": round(statistics.median(b), 1),
                    "peak_uA": round(max(b), 1),
                    "min_uA": round(min(b), 1),
                    "std_uA": round(statistics.stdev(b), 1) if len(b) > 1 else 0,
                    "sample_count": len(b),
                })
    return buckets_out
