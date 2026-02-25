#!/usr/bin/env python3
"""Transport evaluation spike: UDS byte bridge vs FastMCP HTTP.

Self-contained benchmark comparing two transport paths for shoal-orchestrator:

  Path A (stdio):  FastMCP Client → StdioTransport → shoal-mcp-server (direct spawn)
  Path B (http):   FastMCP Client → StreamableHttpTransport → shoal-mcp-server --http

Measures startup latency, tool call latency (p50/p95/p99), concurrent throughput,
and server memory usage.

Usage:
    uv run python benchmarks/transport_spike.py
    uv run python benchmarks/transport_spike.py --calls 100 --concurrency 10
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkResult:
    """Collected measurements for a single transport path."""

    name: str
    startup_ms: float = 0.0
    call_latencies_ms: list[float] = field(default_factory=list)
    concurrent_latencies_ms: list[float] = field(default_factory=list)
    server_rss_kb: int = 0
    error: str = ""

    @property
    def p50(self) -> float:
        if not self.call_latencies_ms:
            return 0.0
        s = sorted(self.call_latencies_ms)
        return s[len(s) // 2]

    @property
    def p95(self) -> float:
        if not self.call_latencies_ms:
            return 0.0
        s = sorted(self.call_latencies_ms)
        return s[int(len(s) * 0.95)]

    @property
    def p99(self) -> float:
        if not self.call_latencies_ms:
            return 0.0
        s = sorted(self.call_latencies_ms)
        return s[int(len(s) * 0.99)]

    @property
    def mean(self) -> float:
        if not self.call_latencies_ms:
            return 0.0
        return statistics.mean(self.call_latencies_ms)

    @property
    def concurrent_mean(self) -> float:
        if not self.concurrent_latencies_ms:
            return 0.0
        return statistics.mean(self.concurrent_latencies_ms)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_rss_kb(pid: int) -> int:
    """Get RSS in KB for a process via /proc (Linux) or ps (fallback)."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    # macOS/fallback
    try:
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True)
        return int(out.strip())
    except (subprocess.CalledProcessError, ValueError):
        return 0


async def _wait_for_http(url: str, max_wait: float = 10.0) -> None:
    """Poll HTTP endpoint until it responds."""
    import httpx

    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=2.0)
                if resp.status_code < 500:
                    return
        except (httpx.ConnectError, httpx.ReadError, OSError):
            pass
        await asyncio.sleep(0.2)
    msg = f"HTTP server at {url} did not become ready in {max_wait}s"
    raise TimeoutError(msg)


# ---------------------------------------------------------------------------
# Benchmark: stdio transport (direct spawn, no pool)
# ---------------------------------------------------------------------------


async def bench_stdio(num_calls: int, concurrency: int) -> BenchmarkResult:
    """Benchmark the stdio transport path (FastMCP Client → StdioTransport)."""
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    result = BenchmarkResult(name="stdio (direct)")

    try:
        # --- Startup latency ---
        transport = StdioTransport(command="shoal-mcp-server", args=[])
        client = Client(transport, timeout=15, init_timeout=10)
        start = time.monotonic()
        async with client:
            result.startup_ms = (time.monotonic() - start) * 1000

            # --- Sequential tool calls ---
            for _ in range(num_calls):
                t0 = time.monotonic()
                await client.call_tool("session_status", {})
                result.call_latencies_ms.append((time.monotonic() - t0) * 1000)

    except Exception as e:
        result.error = str(e)

    return result


# ---------------------------------------------------------------------------
# Benchmark: stdio via pool (proxy → UDS → pool → spawn)
# ---------------------------------------------------------------------------


async def bench_uds_pool(num_calls: int, concurrency: int) -> BenchmarkResult:
    """Benchmark the UDS pool path (StdioTransport → shoal-mcp-proxy → pool)."""
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    result = BenchmarkResult(name="UDS pool (proxy)")

    # Start pool server (blocking Popen is intentional — launches detached process)
    pool_proc = await asyncio.to_thread(
        subprocess.Popen,
        [sys.executable, "-m", "shoal.services.mcp_pool", "bench-spike", "shoal-mcp-server"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        # Wait for socket to appear
        from shoal.services.mcp_pool import mcp_socket

        sock = mcp_socket("bench-spike")
        deadline = time.monotonic() + 5.0
        while not sock.exists() and time.monotonic() < deadline:  # noqa: ASYNC110
            await asyncio.sleep(0.2)
        if not sock.exists():
            result.error = "Pool socket did not appear"
            return result

        # --- Startup latency (proxy → pool → spawn) ---
        transport = StdioTransport(command="shoal-mcp-proxy", args=["bench-spike"])
        client = Client(transport, timeout=15, init_timeout=10)
        start = time.monotonic()
        async with client:
            result.startup_ms = (time.monotonic() - start) * 1000

            # --- Sequential tool calls ---
            for _ in range(num_calls):
                t0 = time.monotonic()
                await client.call_tool("session_status", {})
                result.call_latencies_ms.append((time.monotonic() - t0) * 1000)

            # --- Memory ---
            result.server_rss_kb = _get_rss_kb(pool_proc.pid)

        # --- Concurrent clients ---
        async def _concurrent_call() -> float:
            t = StdioTransport(command="shoal-mcp-proxy", args=["bench-spike"])
            c = Client(t, timeout=15, init_timeout=10)
            async with c:
                t0 = time.monotonic()
                await c.call_tool("session_status", {})
                return (time.monotonic() - t0) * 1000

        tasks = [asyncio.create_task(_concurrent_call()) for _ in range(concurrency)]
        latencies = await asyncio.gather(*tasks, return_exceptions=True)
        for lat in latencies:
            if isinstance(lat, float):
                result.concurrent_latencies_ms.append(lat)

    except Exception as e:
        result.error = str(e)
    finally:
        os.kill(pool_proc.pid, signal.SIGTERM)
        pool_proc.wait(timeout=5)
        # Clean up socket and pid
        from shoal.services.mcp_pool import mcp_pid_file, mcp_socket

        mcp_socket("bench-spike").unlink(missing_ok=True)
        mcp_pid_file("bench-spike").unlink(missing_ok=True)

    return result


# ---------------------------------------------------------------------------
# Benchmark: HTTP transport (streamable-http)
# ---------------------------------------------------------------------------


async def bench_http(num_calls: int, concurrency: int, port: int = 8394) -> BenchmarkResult:
    """Benchmark the HTTP transport path (StreamableHttpTransport → HTTP server)."""
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport

    result = BenchmarkResult(name="HTTP (streamable)")

    # Start HTTP server (blocking Popen is intentional — launches detached process)
    http_proc = await asyncio.to_thread(
        subprocess.Popen,
        ["shoal-mcp-server", "--http", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        await _wait_for_http(f"http://127.0.0.1:{port}/mcp", max_wait=10.0)

        url = f"http://127.0.0.1:{port}/mcp"

        # --- Startup latency (HTTP handshake + MCP initialize) ---
        transport = StreamableHttpTransport(url=url)
        client = Client(transport, timeout=15)
        start = time.monotonic()
        async with client:
            result.startup_ms = (time.monotonic() - start) * 1000

            # --- Sequential tool calls ---
            for _ in range(num_calls):
                t0 = time.monotonic()
                await client.call_tool("session_status", {})
                result.call_latencies_ms.append((time.monotonic() - t0) * 1000)

            # --- Memory ---
            result.server_rss_kb = _get_rss_kb(http_proc.pid)

        # --- Concurrent clients (all hit same HTTP server) ---
        async def _concurrent_call() -> float:
            t = StreamableHttpTransport(url=url)
            c = Client(t, timeout=15)
            async with c:
                t0 = time.monotonic()
                await c.call_tool("session_status", {})
                return (time.monotonic() - t0) * 1000

        tasks = [asyncio.create_task(_concurrent_call()) for _ in range(concurrency)]
        latencies = await asyncio.gather(*tasks, return_exceptions=True)
        for lat in latencies:
            if isinstance(lat, float):
                result.concurrent_latencies_ms.append(lat)

    except Exception as e:
        result.error = str(e)
    finally:
        os.kill(http_proc.pid, signal.SIGTERM)
        http_proc.wait(timeout=5)

    return result


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report(results: list[BenchmarkResult], num_calls: int, concurrency: int) -> None:
    """Print a formatted comparison table."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()

        title = f"Transport Spike Results ({num_calls} calls, {concurrency} concurrent)"
        table = Table(title=title)
        table.add_column("Metric", style="bold")
        for r in results:
            table.add_column(r.name)

        def _fmt(v: float) -> str:
            return f"{v:.1f}ms" if v else "-"

        table.add_row("Startup", *[_fmt(r.startup_ms) for r in results])
        table.add_row("Call p50", *[_fmt(r.p50) for r in results])
        table.add_row("Call p95", *[_fmt(r.p95) for r in results])
        table.add_row("Call p99", *[_fmt(r.p99) for r in results])
        table.add_row("Call mean", *[_fmt(r.mean) for r in results])
        table.add_row(
            "Concurrent mean",
            *[_fmt(r.concurrent_mean) for r in results],
        )
        table.add_row(
            "Server RSS",
            *[f"{r.server_rss_kb:,} KB" if r.server_rss_kb else "-" for r in results],
        )
        table.add_row(
            "Errors",
            *[r.error or "none" for r in results],
        )

        console.print()
        console.print(table)
        console.print()

    except ImportError:
        # Fallback to plain text
        print(f"\n{'Metric':<20}", end="")
        for r in results:
            print(f"{r.name:<25}", end="")
        print()
        print("-" * (20 + 25 * len(results)))
        print(f"{'Startup':<20}", end="")
        for r in results:
            print(f"{r.startup_ms:.1f}ms{'':<19}", end="")
        print()
        print(f"{'Call p50':<20}", end="")
        for r in results:
            print(f"{r.p50:.1f}ms{'':<19}", end="")
        print()
        print(f"{'Call mean':<20}", end="")
        for r in results:
            print(f"{r.mean:.1f}ms{'':<19}", end="")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def async_main(num_calls: int, concurrency: int) -> None:
    """Run all benchmarks and print report."""
    print("Running transport spike benchmarks...")
    print(f"  Calls per transport: {num_calls}")
    print(f"  Concurrent clients:  {concurrency}")
    print()

    # Run stdio first (baseline, simplest path)
    print("[1/3] Benchmarking stdio (direct spawn)...")
    stdio_result = await bench_stdio(num_calls, concurrency)

    # Run UDS pool path
    print("[2/3] Benchmarking UDS pool (proxy → socket → spawn)...")
    uds_result = await bench_uds_pool(num_calls, concurrency)

    # Run HTTP path
    print("[3/3] Benchmarking HTTP (streamable-http)...")
    http_result = await bench_http(num_calls, concurrency)

    print_report([stdio_result, uds_result, http_result], num_calls, concurrency)

    # Summary
    if not http_result.error and not uds_result.error:
        overhead = http_result.mean - uds_result.mean if uds_result.mean else 0
        print(f"HTTP overhead vs UDS pool: {overhead:+.1f}ms per call")
        if http_result.mean > 0 and uds_result.mean > 0:
            ratio = http_result.mean / uds_result.mean
            print(f"HTTP/UDS ratio: {ratio:.2f}x")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Transport evaluation spike benchmark")
    parser.add_argument(
        "--calls",
        type=int,
        default=50,
        help="Sequential calls (default: 50)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="Concurrent clients (default: 5)",
    )
    args = parser.parse_args()

    asyncio.run(async_main(args.calls, args.concurrency))


if __name__ == "__main__":
    main()
