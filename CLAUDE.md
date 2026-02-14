# Test Tools

Testing and measurement tools for embedded BLE and power development.

## Structure

```
test-tools/
├── ble/                        # BLE testing tools
│   ├── uuids.py                # Shared UUID constants
│   ├── gatt_throughput.py      # NUS write/echo/burst tests
│   ├── notification_throughput.py  # Bidirectional rate-controlled throughput
│   └── l2cap_throughput.py     # L2CAP CoC throughput (macOS only)
├── power/                      # Power measurement tools
│   ├── ppk2_utils.py           # Shared PPK2 init and sampling
│   ├── single_test.py          # Single throughput + power run
│   ├── batch_test.py           # N runs with resume + JSON export
│   └── analysis.py             # Analyze batch results
└── tests/                      # Unit tests
    ├── test_uuids.py
    ├── test_throughput_stats.py
    ├── test_power_analysis.py
    └── test_argparse.py
```

## Conventions

- Python 3.11+
- All tools use `argparse` with `build_parser()` exposed for testing
- Class-based tools with structured `to_dict()` / `get_results()` returns
- Run from test-tools/: `python3 -m ble.gatt_throughput --help`
- Run tests: `python3 -m pytest tests/ -v`

## Dependencies

- **bleak**: BLE tools (gatt_throughput, notification_throughput, single_test, batch_test)
- **pyobjc-framework-CoreBluetooth**: l2cap_throughput (macOS only)
- **ppk2-api**: power tools (single_test, batch_test)
- **pyserial**: batch_test (PPK2 serial reset)
- **pytest**: tests

## Adding New Tools

1. Place in the appropriate category directory (ble/, power/, or create new)
2. Add `sys.path.insert(0, str(Path(__file__).parent.parent))` for imports
3. Use `build_parser()` returning ArgumentParser
4. Add a class with structured return method (`to_dict()` or similar)
5. Add tests in tests/
6. Guard optional dependencies with try/except ImportError
7. Update README.md

## Future Categories

- **WiFi Testing**: WiFi throughput, reliability, and range testing
- **Hardware Validation**: GPIO, I2C, SPI peripheral testing
