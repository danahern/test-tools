"""Tests for ThroughputStats from ble.gatt_throughput."""

import time
from unittest.mock import patch
import pytest
from ble.gatt_throughput import ThroughputStats


def test_initial_state():
    stats = ThroughputStats()
    assert stats.bytes_sent == 0
    assert stats.bytes_received == 0
    assert stats.packets_sent == 0
    assert stats.packets_received == 0
    assert stats.latencies == []


def test_tx_throughput():
    stats = ThroughputStats(bytes_sent=10000, start_time=100.0)
    with patch("time.time", return_value=110.0):
        assert stats.tx_throughput() == pytest.approx(1000.0)


def test_rx_throughput():
    stats = ThroughputStats(bytes_received=5000, start_time=100.0)
    with patch("time.time", return_value=110.0):
        assert stats.rx_throughput() == pytest.approx(500.0)


def test_zero_elapsed():
    stats = ThroughputStats(bytes_sent=100, start_time=100.0)
    with patch("time.time", return_value=100.0):
        assert stats.tx_throughput() == 0
        assert stats.rx_throughput() == 0


def test_avg_latency_with_values():
    stats = ThroughputStats(latencies=[0.010, 0.020, 0.030])
    assert stats.avg_latency() == pytest.approx(20.0)


def test_avg_latency_empty():
    stats = ThroughputStats()
    assert stats.avg_latency() == 0


def test_to_dict_structure():
    stats = ThroughputStats(
        bytes_sent=1000,
        bytes_received=2000,
        packets_sent=10,
        packets_received=20,
        start_time=100.0,
        latencies=[0.010, 0.020],
    )
    with patch("time.time", return_value=110.0):
        d = stats.to_dict()

    assert d["duration_s"] == pytest.approx(10.0)
    assert d["bytes_sent"] == 1000
    assert d["bytes_received"] == 2000
    assert d["packets_sent"] == 10
    assert d["packets_received"] == 20
    assert d["tx_throughput_bps"] == pytest.approx(100.0)
    assert d["rx_throughput_bps"] == pytest.approx(200.0)
    assert d["tx_throughput_kbps"] == pytest.approx(0.8)
    assert d["rx_throughput_kbps"] == pytest.approx(1.6)
    assert d["avg_latency_ms"] == pytest.approx(15.0)
    assert d["min_latency_ms"] == pytest.approx(10.0)
    assert d["max_latency_ms"] == pytest.approx(20.0)


def test_to_dict_no_latencies():
    stats = ThroughputStats(bytes_sent=500, start_time=100.0)
    with patch("time.time", return_value=110.0):
        d = stats.to_dict()
    assert "avg_latency_ms" not in d
    assert "min_latency_ms" not in d
    assert "max_latency_ms" not in d


def test_elapsed():
    stats = ThroughputStats(start_time=100.0)
    with patch("time.time", return_value=105.5):
        assert stats.elapsed() == pytest.approx(5.5)
