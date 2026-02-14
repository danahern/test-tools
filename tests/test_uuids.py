"""Tests for ble.uuids constants."""

import re
import pytest
from ble.uuids import (
    NUS_SERVICE_UUID, NUS_RX_CHAR_UUID, NUS_TX_CHAR_UUID,
    NUS_CTRL_CHAR_UUID, RISCV_WORKLOAD_UUID,
    PSM_SERVICE_UUID, PSM_CHAR_UUID,
)

UUID_128_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

ALL_UUIDS = [
    NUS_SERVICE_UUID, NUS_RX_CHAR_UUID, NUS_TX_CHAR_UUID,
    NUS_CTRL_CHAR_UUID, RISCV_WORKLOAD_UUID,
    PSM_SERVICE_UUID, PSM_CHAR_UUID,
]


def test_all_uuids_are_128_bit():
    for uuid in ALL_UUIDS:
        assert UUID_128_RE.match(uuid), f"Invalid UUID format: {uuid}"


def test_nus_uuids_share_base():
    """NUS UUIDs should share the same base (differ only in first segment)."""
    base = NUS_SERVICE_UUID.split("-", 1)[1]
    for uuid in [NUS_RX_CHAR_UUID, NUS_TX_CHAR_UUID, NUS_CTRL_CHAR_UUID, RISCV_WORKLOAD_UUID]:
        assert uuid.split("-", 1)[1] == base, f"{uuid} doesn't share NUS base"


def test_no_duplicate_uuids():
    normalized = [u.lower() for u in ALL_UUIDS]
    assert len(normalized) == len(set(normalized)), "Duplicate UUIDs found"
