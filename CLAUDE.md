# Test Tools Directory

Testing, validation, and utility tools for embedded development.

> **Note:** This folder is named `test-tools/` to avoid collision with west's `tools/` folder (which contains EDTT, net-tools, etc.).

## Available Tools

### ble_throughput.py

BLE throughput testing tool for Nordic UART Service (NUS) devices.

**Capabilities:**
- Scan for BLE devices
- TX throughput testing (sustained writes)
- Echo latency testing (round-trip timing)
- Burst transfer testing
- Detailed statistics reporting

**Usage:**
```bash
# Activate venv first
source zephyr-apps/.venv/bin/activate

# Scan for devices
python test-tools/ble_throughput.py --scan

# Run all tests against a device
python test-tools/ble_throughput.py --name "BLE WiFi Bridge" --test all

# Run specific test
python test-tools/ble_throughput.py --name "BLE Data Transfer" --test echo
```

## Adding New Tools

When adding tools to this directory:

1. Use Python 3.11+ (matches project .python-version)
2. Add dependencies to zephyr-apps/requirements.txt
3. Include argparse CLI with --help
4. Document in this file and README.md

## Tool Categories

- **BLE Testing**: ble_throughput.py
- **WiFi Testing**: (planned)
- **Hardware Validation**: (planned)
