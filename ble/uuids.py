"""Shared BLE UUID constants for all test tools."""

# Nordic UART Service (NUS)
NUS_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_RX_CHAR_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write to device
NUS_TX_CHAR_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Notify from device

# Extended NUS (rate control + workload)
NUS_CTRL_CHAR_UUID = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"  # TX rate control
RISCV_WORKLOAD_UUID = "6e400005-b5a3-f393-e0a9-e50e24dcca9e"  # RISC-V workload

# L2CAP PSM Discovery Service
PSM_SERVICE_UUID = "12345678-1234-5678-1234-56789ABCDEF0"
PSM_CHAR_UUID = "12345678-1234-5678-1234-56789ABCDEF1"
