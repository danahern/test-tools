"""Tests for power.analysis with synthetic data."""

import pytest
from power.analysis import analyze_run, analyze_file
import json
import tempfile
import os


def _make_run(
    run_number=1,
    power_seconds=None,
    throughput_seconds=None,
    voltage_mv=4000,
    total_bytes=100000,
    duration_s=60.0,
):
    """Build a synthetic run dict."""
    if power_seconds is None:
        power_seconds = [
            {
                "elapsed_s": i,
                "avg_uA": 5000.0,
                "median_uA": 4900.0,
                "peak_uA": 8000.0,
                "min_uA": 3000.0,
                "std_uA": 500.0,
                "sample_count": 100000,
                "timestamp": 1000000 + i,
            }
            for i in range(60)
        ]

    if throughput_seconds is None:
        throughput_seconds = [
            {
                "elapsed_s": float(i),
                "instant_kbps": 150.0,
                "avg_kbps": 150.0,
                "total_bytes": total_bytes * i // 60,
                "timestamp": 1000000 + i,
            }
            for i in range(60)
        ]

    return {
        "run_number": run_number,
        "start_time_iso": "2025-01-01T12:00:00",
        "duration_s": duration_s,
        "total_bytes": total_bytes,
        "avg_throughput_kbps": 150.0,
        "ppk2_voltage_mV": voltage_mv,
        "throughput_per_second": throughput_seconds,
        "power_per_second": power_seconds,
    }


def test_analyze_run_basic():
    run = _make_run()
    result = analyze_run(run)
    assert result is not None
    assert result["run"] == 1
    assert result["avg_current_uA"] == pytest.approx(5000.0)
    assert result["peak_current_uA"] == pytest.approx(8000.0)
    assert result["min_current_uA"] == pytest.approx(3000.0)
    assert result["avg_current_mA"] == pytest.approx(5.0)
    # avg_power_mW = 5.0 mA * 4000 mV / 1000 = 20.0 mW
    assert result["avg_power_mW"] == pytest.approx(20.0)
    assert "energy_per_bit_nJ" in result
    assert "energy_per_byte_nJ" in result
    assert result["energy_per_byte_nJ"] == pytest.approx(result["energy_per_bit_nJ"] * 8, abs=1.0)


def test_analyze_run_empty_power():
    run = _make_run(power_seconds=[])
    result = analyze_run(run)
    assert result is None


def test_analyze_run_single_data_point():
    """Single power data point should not crash (stdev needs >1)."""
    run = _make_run(power_seconds=[{
        "elapsed_s": 0,
        "avg_uA": 5000.0,
        "median_uA": 5000.0,
        "peak_uA": 5000.0,
        "min_uA": 5000.0,
        "std_uA": 0,
        "sample_count": 1000,
        "timestamp": 1000000,
    }])
    result = analyze_run(run)
    assert result is not None
    assert result["current_std_uA"] == 0


def test_steady_state_filtering():
    """Throughput data before steady_state_s should be excluded."""
    throughput = []
    for i in range(30):
        # First 15s: 50 kbps (ramp-up), after: 150 kbps
        kbps = 50.0 if i < 15 else 150.0
        throughput.append({
            "elapsed_s": float(i),
            "instant_kbps": kbps,
            "avg_kbps": kbps,
            "total_bytes": 0,
            "timestamp": 1000000 + i,
        })

    run = _make_run(throughput_seconds=throughput)
    result = analyze_run(run, steady_state_s=15)
    # Should only use data from elapsed_s >= 15, which is all 150 kbps
    assert result["throughput_kbps"] == pytest.approx(150.0)


def test_energy_per_bit_calculation():
    """Verify nJ/bit with known values."""
    # avg_mW = 20.0, throughput = 150 kbps = 150000 bps
    # nJ/bit = (20.0 * 1e6) / 150000 = 133.3
    run = _make_run()
    result = analyze_run(run)
    expected_nj = (20.0 * 1e6) / 150000
    assert result["energy_per_bit_nJ"] == pytest.approx(expected_nj, rel=0.01)


def test_analyze_file():
    """Test analyze_file with a temporary JSON file."""
    data = {
        "config": {
            "device_name": "test",
            "ppk2_voltage_mV": 4000,
            "measure_duration_s": 60,
            "settle_time_s": 10,
            "num_runs": 2,
        },
        "runs": [_make_run(run_number=1), _make_run(run_number=2)],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmpfile = f.name

    try:
        result = analyze_file(tmpfile)
        assert result["num_runs"] == 2
        assert len(result["per_run"]) == 2
        assert "aggregate" in result
        assert result["aggregate"]["throughput_kbps_avg"] == pytest.approx(150.0)
        assert result["aggregate"]["total_bytes"] == 200000
    finally:
        os.unlink(tmpfile)


def test_analyze_file_no_valid_runs():
    """analyze_file with empty power data returns error."""
    data = {
        "config": {"ppk2_voltage_mV": 4000, "num_runs": 1,
                    "measure_duration_s": 60, "settle_time_s": 10},
        "runs": [_make_run(power_seconds=[])],
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmpfile = f.name

    try:
        result = analyze_file(tmpfile)
        assert "error" in result
    finally:
        os.unlink(tmpfile)
