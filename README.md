# Test Tools

Testing and measurement tools for embedded BLE and power development.

> **Note:** Named `test-tools/` to avoid collision with west's `tools/` directory.

## Prerequisites

```bash
# Activate the project venv
source zephyr-apps/.venv/bin/activate

# Install dependencies
pip install bleak ppk2-api pytest
# macOS L2CAP support:
pip install pyobjc-framework-CoreBluetooth
```

## BLE Tools

### GATT Throughput (`ble.gatt_throughput`)

Tests TX, echo latency, and burst throughput using Nordic UART Service (NUS).

```bash
python3 -m ble.gatt_throughput --scan
python3 -m ble.gatt_throughput --name "BLE Data Transfer" --test all
python3 -m ble.gatt_throughput --name "MyDevice" --test echo --duration 30
python3 -m ble.gatt_throughput --addr "AA:BB:CC:DD:EE:FF" --test tx --size 200
```

| Option | Description |
|--------|-------------|
| `--scan` | Scan for devices only |
| `--name NAME` | Device name to connect to |
| `--addr ADDR` | Device MAC address |
| `--test {tx,echo,burst,all}` | Test type (default: all) |
| `--duration SECS` | Duration in seconds (default: 10) |
| `--size BYTES` | Packet size (default: 20, max ~240) |
| `--packets NUM` | Burst packet count (default: 100) |

### Notification Throughput (`ble.notification_throughput`)

Bidirectional BLE throughput with independent rate control for host and device. Supports RISC-V workload configuration on dual-core firmware.

```bash
python3 -m ble.notification_throughput
python3 -m ble.notification_throughput --mac-tx 100 --device-tx 50
python3 -m ble.notification_throughput --name nRF54L15_Dual --workload 6
python3 -m ble.notification_throughput --mac-tx 0 --device-tx 50  # RX only
```

| Option | Description |
|--------|-------------|
| `--name NAME` | Device name (default: nRF54L15_Test) |
| `--mac-tx KBPS` | Host TX rate (0=disabled, omit=max) |
| `--device-tx KBPS` | Device TX rate (0=disabled, omit=max) |
| `--workload 0-13` | RISC-V workload (0=Idle...13=Full Necklace) |
| `--packet-size BYTES` | Packet size (default: 495) |
| `--scan-timeout SECS` | Scan timeout (default: 10) |

### L2CAP Throughput (`ble.l2cap_throughput`)

L2CAP Connection-Oriented Channel throughput via CoreBluetooth. **macOS only.**

```bash
python3 -m ble.l2cap_throughput
python3 -m ble.l2cap_throughput --name nRF54L15_Test --duration 30
```

| Option | Description |
|--------|-------------|
| `--name NAME` | Device name (default: nRF54L15_Test) |
| `--duration SECS` | Duration (0=run forever) |
| `--scan-timeout SECS` | Scan timeout (default: 15) |

## Power Tools

All power tools require a Nordic PPK2 connected via USB.

### Single Test (`power.single_test`)

One-shot BLE throughput + PPK2 power measurement.

```bash
python3 -m power.single_test --ppk2-port /dev/tty.usbmodemXXXX
python3 -m power.single_test --ppk2-port /dev/tty.usbmodemXXXX --duration 60 --voltage 3300
```

| Option | Description |
|--------|-------------|
| `--ppk2-port PORT` | **Required.** PPK2 serial port |
| `--name NAME` | Device name (default: nRF54L15_Test) |
| `--voltage MV` | Source voltage in mV (default: 4000) |
| `--duration SECS` | Measurement duration (default: 30) |
| `--settle-time SECS` | Pre-measurement settle (default: 5) |
| `--boot-wait SECS` | Device boot wait (default: 4) |
| `--scan-timeout SECS` | BLE scan timeout (default: 10) |

### Batch Test (`power.batch_test`)

Multiple consecutive runs with resume support and JSON export.

```bash
python3 -m power.batch_test --ppk2-port /dev/tty.usbmodemXXXX
python3 -m power.batch_test --ppk2-port /dev/tty.usbmodemXXXX --num-runs 5 --duration 60
```

| Option | Description |
|--------|-------------|
| `--ppk2-port PORT` | **Required.** PPK2 serial port |
| `--name NAME` | Device name (default: nRF54L15_Test) |
| `--voltage MV` | Source voltage (default: 4000) |
| `--duration SECS` | Per-run duration (default: 300) |
| `--settle-time SECS` | Settle time (default: 10) |
| `--num-runs N` | Number of runs (default: 10) |
| `--output FILE` | Output JSON file (default: power_throughput_raw.json) |
| `--scan-timeout SECS` | BLE scan timeout (default: 15) |

### Analysis (`power.analysis`)

Analyze batch test results: per-run stats, aggregates, time series.

```bash
python3 -m power.analysis --input power_throughput_raw.json
python3 -m power.analysis --input results.json --steady-state 20
```

| Option | Description |
|--------|-------------|
| `--input FILE` | Input JSON file (default: power_throughput_raw.json) |
| `--steady-state SECS` | Ramp-up exclusion period (default: 15) |

## Running Tests

```bash
cd test-tools
python3 -m pytest tests/ -v
```

## Troubleshooting

**Device not found:**
- Ensure device is powered and advertising
- Check no other app is connected to it
- On macOS, grant Bluetooth permissions to Terminal

**PPK2 connection issues:**
- Find port: `ls /dev/tty.usbmodem*`
- Ensure no other app (nRF Connect Power Profiler) is using the PPK2
- Try unplugging and reconnecting

**L2CAP test fails to import:**
- macOS only; requires `pip install pyobjc-framework-CoreBluetooth`
