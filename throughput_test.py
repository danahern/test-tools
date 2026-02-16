#!/usr/bin/env python3
"""TCP throughput test tool.

Connects to a device running the wifi_provision throughput server
and measures upload, download, or bidirectional throughput.

Uses only Python standard library (no external dependencies).

Protocol:
  Client sends 1-byte command:
    0x01 = echo (client sends, server echoes back)
    0x02 = sink (client sends, server discards)
    0x03 = source (server sends, client discards)
  Then data flows for the specified duration.
"""

import argparse
import socket
import statistics
import sys
import time

DEFAULT_PORT = 4242
DEFAULT_DURATION = 10
DEFAULT_BLOCK_SIZE = 4096

CMD_ECHO = 0x01
CMD_SINK = 0x02
CMD_SOURCE = 0x03


def format_throughput(bytes_per_sec: float) -> str:
    """Format throughput in human-readable units."""
    bits = bytes_per_sec * 8
    if bits >= 1_000_000:
        return f"{bits / 1_000_000:.2f} Mbps"
    if bits >= 1_000:
        return f"{bits / 1_000:.2f} Kbps"
    return f"{bits:.0f} bps"


def run_upload(sock: socket.socket, duration: float, block_size: int) -> dict:
    """Send data as fast as possible (sink mode)."""
    sock.sendall(bytes([CMD_SINK]))
    data = bytes(block_size)
    stats = []
    start = time.monotonic()
    interval_start = start
    interval_bytes = 0

    while True:
        now = time.monotonic()
        elapsed = now - start
        if elapsed >= duration:
            break

        try:
            sent = sock.send(data)
            interval_bytes += sent
        except (BrokenPipeError, ConnectionResetError):
            break

        if now - interval_start >= 1.0:
            rate = interval_bytes / (now - interval_start)
            stats.append(rate)
            print(f"  [{elapsed:.0f}s] {format_throughput(rate)}")
            interval_start = now
            interval_bytes = 0

    total_elapsed = time.monotonic() - start
    if interval_bytes > 0 and stats:
        rate = interval_bytes / (time.monotonic() - interval_start)
        stats.append(rate)

    return {"direction": "upload", "stats": stats, "duration": total_elapsed}


def run_download(sock: socket.socket, duration: float, block_size: int) -> dict:
    """Receive data as fast as possible (source mode)."""
    sock.sendall(bytes([CMD_SOURCE]))
    sock.settimeout(2.0)
    stats = []
    start = time.monotonic()
    interval_start = start
    interval_bytes = 0

    while True:
        now = time.monotonic()
        elapsed = now - start
        if elapsed >= duration:
            break

        try:
            data = sock.recv(block_size)
            if not data:
                break
            interval_bytes += len(data)
        except socket.timeout:
            break

        if now - interval_start >= 1.0:
            rate = interval_bytes / (now - interval_start)
            stats.append(rate)
            print(f"  [{elapsed:.0f}s] {format_throughput(rate)}")
            interval_start = now
            interval_bytes = 0

    total_elapsed = time.monotonic() - start
    if interval_bytes > 0 and stats:
        rate = interval_bytes / (time.monotonic() - interval_start)
        stats.append(rate)

    return {"direction": "download", "stats": stats, "duration": total_elapsed}


def run_echo(sock: socket.socket, duration: float, block_size: int) -> dict:
    """Send and receive (echo mode) for round-trip throughput."""
    sock.sendall(bytes([CMD_ECHO]))
    sock.settimeout(5.0)
    send_data = bytes(block_size)
    stats = []
    start = time.monotonic()
    interval_start = start
    interval_bytes = 0

    while True:
        now = time.monotonic()
        elapsed = now - start
        if elapsed >= duration:
            break

        try:
            sock.sendall(send_data)
            received = 0
            while received < block_size:
                chunk = sock.recv(block_size - received)
                if not chunk:
                    break
                received += len(chunk)
            interval_bytes += received
        except (socket.timeout, BrokenPipeError, ConnectionResetError):
            break

        if now - interval_start >= 1.0:
            rate = interval_bytes / (now - interval_start)
            stats.append(rate)
            print(f"  [{elapsed:.0f}s] {format_throughput(rate)}")
            interval_start = now
            interval_bytes = 0

    total_elapsed = time.monotonic() - start
    if interval_bytes > 0 and stats:
        rate = interval_bytes / (time.monotonic() - interval_start)
        stats.append(rate)

    return {"direction": "echo", "stats": stats, "duration": total_elapsed}


def print_summary(result: dict):
    """Print test summary."""
    stats = result["stats"]
    if not stats:
        print("\nNo data collected.")
        return

    avg = statistics.mean(stats)
    print(f"\n--- {result['direction']} summary ---")
    print(f"Duration:   {result['duration']:.1f}s")
    print(f"Avg:        {format_throughput(avg)}")
    if len(stats) > 1:
        print(f"Min:        {format_throughput(min(stats))}")
        print(f"Max:        {format_throughput(max(stats))}")
        stdev = statistics.stdev(stats)
        jitter_pct = (stdev / avg * 100) if avg > 0 else 0
        print(f"Jitter:     {jitter_pct:.1f}%")


def main():
    parser = argparse.ArgumentParser(
        description="TCP throughput test tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s 192.168.1.50 upload
  %(prog)s 192.168.1.50 download -d 30
  %(prog)s 192.168.1.50 echo -b 1024
""",
    )
    parser.add_argument("host", help="Device IP address")
    parser.add_argument(
        "mode",
        choices=["upload", "download", "echo"],
        help="Test mode",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=DEFAULT_PORT, help=f"TCP port (default: {DEFAULT_PORT})"
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
        help=f"Test duration in seconds (default: {DEFAULT_DURATION})",
    )
    parser.add_argument(
        "-b",
        "--block-size",
        type=int,
        default=DEFAULT_BLOCK_SIZE,
        help=f"Block size in bytes (default: {DEFAULT_BLOCK_SIZE})",
    )

    args = parser.parse_args()

    print(f"Connecting to {args.host}:{args.port}...")
    try:
        sock = socket.create_connection((args.host, args.port), timeout=5)
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    sock.settimeout(None)  # Remove connect timeout for data transfer
    print(f"Connected. Running {args.mode} test for {args.duration}s...")

    modes = {
        "upload": run_upload,
        "download": run_download,
        "echo": run_echo,
    }

    try:
        result = modes[args.mode](sock, args.duration, args.block_size)
        print_summary(result)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
