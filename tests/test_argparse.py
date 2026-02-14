"""Tests for CLI argument parsing across all tools."""

import sys
import pytest
from ble.gatt_throughput import build_parser as gatt_parser
from ble.notification_throughput import build_parser as notif_parser
from power.analysis import build_parser as analysis_parser

# l2cap_throughput is macOS-only; import conditionally
if sys.platform == "darwin":
    from ble.l2cap_throughput import build_parser as l2cap_parser
else:
    l2cap_parser = None

# power tools import ppk2_utils which has optional deps; parsers are safe to import
from power.single_test import build_parser as single_parser
from power.batch_test import build_parser as batch_parser


class TestGattParser:
    def test_defaults(self):
        args = gatt_parser().parse_args([])
        assert args.test == "all"
        assert args.duration == 10.0
        assert args.size == 20
        assert args.packets == 100
        assert args.scan is False

    def test_scan_flag(self):
        args = gatt_parser().parse_args(["--scan"])
        assert args.scan is True

    def test_all_options(self):
        args = gatt_parser().parse_args([
            "--name", "MyDevice", "--test", "echo",
            "--duration", "30", "--size", "200"
        ])
        assert args.name == "MyDevice"
        assert args.test == "echo"
        assert args.duration == 30.0
        assert args.size == 200

    def test_invalid_test_type(self):
        with pytest.raises(SystemExit):
            gatt_parser().parse_args(["--test", "invalid"])


class TestNotifParser:
    def test_defaults(self):
        args = notif_parser().parse_args([])
        assert args.name == "nRF54L15_Test"
        assert args.mac_tx is None
        assert args.device_tx is None
        assert args.workload is None
        assert args.packet_size == 495
        assert args.scan_timeout == 10.0

    def test_workload_valid(self):
        args = notif_parser().parse_args(["--workload", "6"])
        assert args.workload == 6

    def test_workload_invalid(self):
        with pytest.raises(SystemExit):
            notif_parser().parse_args(["--workload", "99"])

    def test_rate_args(self):
        args = notif_parser().parse_args(["--mac-tx", "100", "--device-tx", "50"])
        assert args.mac_tx == 100
        assert args.device_tx == 50


@pytest.mark.skipif(l2cap_parser is None, reason="macOS only")
class TestL2capParser:
    def test_defaults(self):
        args = l2cap_parser().parse_args([])
        assert args.name == "nRF54L15_Test"
        assert args.duration == 0
        assert args.scan_timeout == 15

    def test_all_options(self):
        args = l2cap_parser().parse_args([
            "--name", "TestDev", "--duration", "30", "--scan-timeout", "20"
        ])
        assert args.name == "TestDev"
        assert args.duration == 30
        assert args.scan_timeout == 20


class TestSingleParser:
    def test_ppk2_port_required(self):
        with pytest.raises(SystemExit):
            single_parser().parse_args([])

    def test_defaults_with_port(self):
        args = single_parser().parse_args(["--ppk2-port", "/dev/ttyUSB0"])
        assert args.ppk2_port == "/dev/ttyUSB0"
        assert args.name == "nRF54L15_Test"
        assert args.voltage == 4000
        assert args.duration == 30
        assert args.settle_time == 5
        assert args.boot_wait == 4
        assert args.scan_timeout == 10.0

    def test_invalid_duration_type(self):
        with pytest.raises(SystemExit):
            single_parser().parse_args(["--ppk2-port", "/dev/x", "--duration", "abc"])


class TestBatchParser:
    def test_ppk2_port_required(self):
        with pytest.raises(SystemExit):
            batch_parser().parse_args([])

    def test_defaults_with_port(self):
        args = batch_parser().parse_args(["--ppk2-port", "/dev/ttyUSB0"])
        assert args.ppk2_port == "/dev/ttyUSB0"
        assert args.name == "nRF54L15_Test"
        assert args.voltage == 4000
        assert args.duration == 300
        assert args.settle_time == 10
        assert args.num_runs == 10
        assert args.output == "power_throughput_raw.json"
        assert args.scan_timeout == 15.0


class TestAnalysisParser:
    def test_defaults(self):
        args = analysis_parser().parse_args([])
        assert args.input == "power_throughput_raw.json"
        assert args.steady_state == 15

    def test_custom_args(self):
        args = analysis_parser().parse_args(["--input", "data.json", "--steady-state", "20"])
        assert args.input == "data.json"
        assert args.steady_state == 20
