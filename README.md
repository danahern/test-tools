# Test Tools

Testing, validation, and utility tools for embedded development workflows.

> **Note:** This folder is named `test-tools/` to avoid collision with west's `tools/` folder (EDTT, net-tools, etc.).

## Prerequisites

Ensure the virtual environment is activated:
```bash
cd /path/to/workspace
source zephyr-apps/.venv/bin/activate
```

## BLE Throughput Tester

A Python tool for testing BLE throughput with devices using Nordic UART Service (NUS).

### Features

- **Device scanning**: Find BLE devices in range
- **TX throughput**: Measure sustained write performance
- **Echo latency**: Round-trip timing with echo responses
- **Burst transfers**: Packet burst testing with statistics

### Usage

```bash
# Scan for BLE devices
python test-tools/ble_throughput.py --scan

# Connect by device name and run all tests
python test-tools/ble_throughput.py --name "BLE Data Transfer" --test all

# Connect by MAC address and run specific test
python test-tools/ble_throughput.py --addr "AA:BB:CC:DD:EE:FF" --test echo

# TX test with custom parameters
python test-tools/ble_throughput.py --name "BLE Data Transfer" --test tx --duration 30 --size 200

# Burst test
python test-tools/ble_throughput.py --name "BLE Data Transfer" --test burst --packets 500 --size 100
```

### Options

| Option | Description |
|--------|-------------|
| `--scan` | Scan for BLE devices only |
| `--name NAME` | Device name to connect to |
| `--addr ADDR` | Device MAC address to connect to |
| `--test {tx,echo,burst,all}` | Test type to run (default: all) |
| `--duration SECS` | Test duration in seconds (default: 10) |
| `--size BYTES` | Packet size in bytes (default: 20, max ~240) |
| `--packets NUM` | Number of packets for burst test (default: 100) |

### Example Output

```
==================================================
THROUGHPUT TEST RESULTS
==================================================
Duration:        10.05 sec
Packets sent:    892
Packets recv:    891
Bytes sent:      17,840
Bytes received:  22,275
TX throughput:   1775.12 B/s (14.20 kbit/s)
RX throughput:   2216.42 B/s (17.73 kbit/s)
Avg latency:     11.24 ms
Min latency:     8.12 ms
Max latency:     45.67 ms
==================================================
```

### Troubleshooting

**Device not found:**
- Ensure device is powered and advertising
- Check no other app is connected to it
- On macOS, grant Bluetooth permissions to Terminal

**Connection fails:**
- Move closer to the device
- Try scanning first to verify device is visible
- Check device firmware is running correctly

## Planned Tools

- **WiFi throughput tester**: Test WiFi data rates and reliability
- **Hardware validation**: GPIO, I2C, SPI peripheral testing
- **Power profiling**: Current consumption analysis
