#!/usr/bin/env python3
"""
MCP vs Native Function Latency Benchmark

Compares latency of:
1. Native FastAPI function calls (direct HTTP)
2. MCP SSE protocol calls (Model Context Protocol)

Usage:
    cd benchmarks
    docker-compose -f docker-compose.mcp-benchmark.yml up -d
    uv run benchmark_latency.py [--iterations 100] [--warmup 10]
    docker-compose -f docker-compose.mcp-benchmark.yml down

Output:
    - Latency statistics (p50, p95, p99, std)
    - Comparison chart
    - Recommendation based on latency thresholds
"""

import asyncio
import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager

import httpx

# Add parent src to path
sys.path.insert(0, '/Users/shahid/dev/Projects/voice_ai/src')


@dataclass
class LatencyResult:
    """Single latency measurement."""
    method: str  # 'native' or 'mcp'
    operation: str  # 'list_tickets', 'get_ticket', etc.
    latency_ms: float
    timestamp: float
    success: bool
    error: Optional[str] = None


@dataclass
class BenchmarkStats:
    """Statistics for a benchmark run."""
    method: str
    operation: str
    iterations: int
    successes: int
    failures: int
    min_ms: float
    max_ms: float
    mean_ms: float
    median_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    std_ms: float


class NativeClient:
    """Client for native FastAPI endpoints."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def health_check(self) -> bool:
        """Check if API is healthy."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
    
    async def list_tickets(self) -> tuple[List[Dict], float]:
        """List all tickets, return (data, latency_ms)."""
        start = time.perf_counter()
        response = await self.client.get(f"{self.base_url}/tickets")
        latency = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        return response.json(), latency
    
    async def get_ticket(self, ticket_id: str) -> tuple[Dict, float]:
        """Get specific ticket, return (data, latency_ms)."""
        start = time.perf_counter()
        response = await self.client.get(f"{self.base_url}/tickets/{ticket_id}")
        latency = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        return response.json(), latency
    
    async def sync_status(self) -> tuple[Dict, float]:
        """Get sync status, return (data, latency_ms)."""
        start = time.perf_counter()
        response = await self.client.get(f"{self.base_url}/sync/status")
        latency = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        return response.json(), latency
    
    async def close(self):
        await self.client.aclose()


class MCPClient:
    """Client for MCP SSE endpoints."""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.session_id: Optional[str] = None
    
    async def health_check(self) -> bool:
        """Check if MCP server is healthy."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception:
            return False
    
    async def initialize(self):
        """Initialize MCP session."""
        # For SSE transport, we need to establish a session
        # This is a simplified version - real MCP uses SSE streams
        response = await self.client.post(
            f"{self.base_url}/initialize",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "benchmark", "version": "1.0.0"}
                }
            }
        )
        response.raise_for_status()
        result = response.json()
        if "result" in result:
            self.session_id = result["result"].get("sessionId")
    
    async def _call_tool(self, tool_name: str, arguments: Dict) -> tuple[Any, float]:
        """Call an MCP tool, return (result, latency_ms)."""
        start = time.perf_counter()
        
        headers = {}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        
        response = await self.client.post(
            f"{self.base_url}/tools/call",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
        )
        latency = (time.perf_counter() - start) * 1000
        response.raise_for_status()
        return response.json(), latency
    
    async def list_tickets(self) -> tuple[List[Dict], float]:
        """List all tickets via MCP."""
        result, latency = await self._call_tool(
            "execute_sql",
            {"query": "SELECT * FROM reservation_tickets ORDER BY created_at DESC"}
        )
        # Extract data from MCP result
        if "result" in result and "content" in result["result"]:
            data = json.loads(result["result"]["content"][0]["text"])
            return data, latency
        return [], latency
    
    async def get_ticket(self, ticket_id: str) -> tuple[Dict, float]:
        """Get specific ticket via MCP."""
        result, latency = await self._call_tool(
            "execute_sql",
            {"query": f"SELECT * FROM reservation_tickets WHERE ticket_id = '{ticket_id}'"}
        )
        if "result" in result and "content" in result["result"]:
            data = json.loads(result["result"]["content"][0]["text"])
            return data[0] if data else {}, latency
        return {}, latency
    
    async def sync_status(self) -> tuple[Dict, float]:
        """Get sync status via MCP."""
        # Use get_object_details or execute_sql
        result, latency = await self._call_tool(
            "execute_sql",
            {"query": "SELECT * FROM sync_status ORDER BY last_sync_at DESC LIMIT 1"}
        )
        if "result" in result and "content" in result["result"]:
            data = json.loads(result["result"]["content"][0]["text"])
            return {"sync_status": data[0] if data else None}, latency
        return {"sync_status": None}, latency
    
    async def close(self):
        await self.client.aclose()


async def wait_for_services(native: NativeClient, mcp: MCPClient, max_wait: int = 60):
    """Wait for both services to be healthy."""
    print("⏳ Waiting for services to be ready...")
    start = time.time()
    
    native_ready = False
    mcp_ready = False
    
    while time.time() - start < max_wait:
        if not native_ready:
            native_ready = await native.health_check()
            if native_ready:
                print("  ✅ Native API ready")
        
        if not mcp_ready:
            mcp_ready = await mcp.health_check()
            if mcp_ready:
                print("  ✅ MCP Server ready")
        
        if native_ready and mcp_ready:
            return True
        
        await asyncio.sleep(1)
    
    return False


async def run_benchmark(
    client,
    method_name: str,
    operation: str,
    iterations: int,
    warmup: int
) -> List[LatencyResult]:
    """Run benchmark for a specific operation."""
    results = []
    
    # Warmup
    print(f"  Warming up {method_name}/{operation}...")
    for _ in range(warmup):
        try:
            if operation == "list_tickets":
                await client.list_tickets()
            elif operation == "get_ticket":
                # Use a dummy ID for warmup
                await client.get_ticket("LOTUS-0001")
            elif operation == "sync_status":
                await client.sync_status()
        except Exception as e:
            print(f"    Warmup error (ok): {e}")
    
    # Benchmark
    print(f"  Running {iterations} iterations...")
    for i in range(iterations):
        try:
            if operation == "list_tickets":
                _, latency = await client.list_tickets()
                results.append(LatencyResult(
                    method=method_name,
                    operation=operation,
                    latency_ms=latency,
                    timestamp=time.time(),
                    success=True
                ))
            elif operation == "get_ticket":
                # Get first ticket ID from list
                tickets, _ = await client.list_tickets()
                if tickets:
                    ticket_id = tickets[0].get("ticket_id", "LOTUS-0001")
                    _, latency = await client.get_ticket(ticket_id)
                    results.append(LatencyResult(
                        method=method_name,
                        operation=operation,
                        latency_ms=latency,
                        timestamp=time.time(),
                        success=True
                    ))
            elif operation == "sync_status":
                _, latency = await client.sync_status()
                results.append(LatencyResult(
                    method=method_name,
                    operation=operation,
                    latency_ms=latency,
                    timestamp=time.time(),
                    success=True
                ))
        except Exception as e:
            results.append(LatencyResult(
                method=method_name,
                operation=operation,
                latency_ms=0,
                timestamp=time.time(),
                success=False,
                error=str(e)
            ))
        
        if (i + 1) % 10 == 0:
            print(f"    Completed {i + 1}/{iterations}")
    
    return results


def calculate_stats(results: List[LatencyResult]) -> BenchmarkStats:
    """Calculate statistics from latency results."""
    latencies = [r.latency_ms for r in results if r.success]
    
    if not latencies:
        return BenchmarkStats(
            method=results[0].method if results else "unknown",
            operation=results[0].operation if results else "unknown",
            iterations=len(results),
            successes=0,
            failures=len(results),
            min_ms=0, max_ms=0, mean_ms=0, median_ms=0,
            p50_ms=0, p95_ms=0, p99_ms=0, std_ms=0
        )
    
    latencies.sort()
    n = len(latencies)
    
    return BenchmarkStats(
        method=results[0].method,
        operation=results[0].operation,
        iterations=len(results),
        successes=sum(1 for r in results if r.success),
        failures=sum(1 for r in results if not r.success),
        min_ms=min(latencies),
        max_ms=max(latencies),
        mean_ms=statistics.mean(latencies),
        median_ms=statistics.median(latencies),
        p50_ms=latencies[int(n * 0.50)],
        p95_ms=latencies[int(n * 0.95)] if n > 20 else latencies[-1],
        p99_ms=latencies[int(n * 0.99)] if n > 100 else latencies[-1],
        std_ms=statistics.stdev(latencies) if n > 1 else 0
    )


def print_comparison(native_stats: BenchmarkStats, mcp_stats: BenchmarkStats):
    """Print comparison table."""
    print("\n" + "=" * 80)
    print(f"LATENCY COMPARISON: {native_stats.operation.upper()}")
    print("=" * 80)
    
    print(f"\n{'Metric':<20} {'Native (ms)':>15} {'MCP (ms)':>15} {'Overhead':>15}")
    print("-" * 80)
    
    metrics = [
        ("Min", native_stats.min_ms, mcp_stats.min_ms),
        ("Max", native_stats.max_ms, mcp_stats.max_ms),
        ("Mean", native_stats.mean_ms, mcp_stats.mean_ms),
        ("Median", native_stats.median_ms, mcp_stats.median_ms),
        ("P50", native_stats.p50_ms, mcp_stats.p50_ms),
        ("P95", native_stats.p95_ms, mcp_stats.p95_ms),
        ("P99", native_stats.p99_ms, mcp_stats.p99_ms),
        ("Std Dev", native_stats.std_ms, mcp_stats.std_ms),
    ]
    
    for name, native_val, mcp_val in metrics:
        overhead = mcp_val - native_val
        overhead_pct = (overhead / native_val * 100) if native_val > 0 else 0
        print(f"{name:<20} {native_val:>15.2f} {mcp_val:>15.2f} {f'+{overhead:.2f}ms ({overhead_pct:.1f}%)':>15}")
    
    print("\n" + "=" * 80)
    
    # Recommendation
    mean_overhead = mcp_stats.mean_ms - native_stats.mean_ms
    p95_overhead = mcp_stats.p95_ms - native_stats.p95_ms
    
    print("\n📊 RECOMMENDATION:")
    if p95_overhead < 20:
        print("  ✅ MCP overhead is minimal (<20ms). Either protocol works.")
        print("     Consider MCP for better isolation and tool discoverability.")
    elif p95_overhead < 50:
        print("  ⚠️  MCP overhead is moderate (20-50ms). Borderline for voice AI.")
        print("     Use native for latency-critical paths, MCP for admin tools.")
    else:
        print("  ❌ MCP overhead is significant (>50ms). Not recommended for voice AI.")
        print("     Stick with native functions for production voice paths.")
    
    # Voice AI specific guidance
    print("\n🎙️  VOICE AI CONTEXT:")
    total_native = native_stats.p95_ms + 100  # +100ms for LLM processing
    total_mcp = mcp_stats.p95_ms + 100
    
    if total_native < 300:
        print(f"  Native total latency: ~{total_native:.0f}ms (✅ Good for real-time voice)")
    else:
        print(f"  Native total latency: ~{total_native:.0f}ms (⚠️  Getting slow for voice)")
    
    if total_mcp < 300:
        print(f"  MCP total latency:    ~{total_mcp:.0f}ms (✅ Good for real-time voice)")
    else:
        print(f"  MCP total latency:    ~{total_mcp:.0f}ms (❌ Too slow for real-time voice)")
    
    print("=" * 80)


def save_results(results: Dict[str, Any], filename: str = None):
    """Save results to JSON file."""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"benchmark_results_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=lambda x: asdict(x) if hasattr(x, '__dataclass_fields__') else str(x))
    
    print(f"\n💾 Results saved to: {filename}")


async def main():
    parser = argparse.ArgumentParser(
        description="Benchmark MCP vs Native Function Latency"
    )
    parser.add_argument(
        "--iterations", "-i",
        type=int,
        default=100,
        help="Number of benchmark iterations (default: 100)"
    )
    parser.add_argument(
        "--warmup", "-w",
        type=int,
        default=10,
        help="Number of warmup iterations (default: 10)"
    )
    parser.add_argument(
        "--operations", "-o",
        nargs="+",
        default=["list_tickets", "sync_status"],
        choices=["list_tickets", "get_ticket", "sync_status"],
        help="Operations to benchmark"
    )
    parser.add_argument(
        "--output", "-f",
        type=str,
        help="Output file for results (JSON)"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("🚀 MCP vs NATIVE FUNCTION LATENCY BENCHMARK")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  Iterations per operation: {args.iterations}")
    print(f"  Warmup iterations: {args.warmup}")
    print(f"  Operations: {', '.join(args.operations)}")
    print()
    
    # Create clients
    native = NativeClient("http://localhost:8000")
    mcp = MCPClient("http://localhost:8080")
    
    try:
        # Wait for services
        if not await wait_for_services(native, mcp):
            print("❌ Services failed to start within timeout")
            return 1
        
        # Initialize MCP session
        print("\n🔌 Initializing MCP session...")
        try:
            await mcp.initialize()
            print("  ✅ MCP session initialized")
        except Exception as e:
            print(f"  ⚠️  MCP initialization error (may be ok): {e}")
        
        all_results = {
            "config": {
                "iterations": args.iterations,
                "warmup": args.warmup,
                "operations": args.operations,
                "timestamp": datetime.now().isoformat()
            },
            "results": {}
        }
        
        # Run benchmarks for each operation
        for operation in args.operations:
            print(f"\n📋 Benchmarking: {operation}")
            
            # Native benchmark
            print(f"  Native API...")
            native_results = await run_benchmark(
                native, "native", operation, args.iterations, args.warmup
            )
            native_stats = calculate_stats(native_results)
            
            # MCP benchmark
            print(f"  MCP...")
            mcp_results = await run_benchmark(
                mcp, "mcp", operation, args.iterations, args.warmup
            )
            mcp_stats = calculate_stats(mcp_results)
            
            # Print comparison
            print_comparison(native_stats, mcp_stats)
            
            # Store results
            all_results["results"][operation] = {
                "native": asdict(native_stats),
                "mcp": asdict(mcp_stats),
                "raw_native": [asdict(r) for r in native_results],
                "raw_mcp": [asdict(r) for r in mcp_results]
            }
        
        # Save results
        save_results(all_results, args.output)
        
        print("\n✅ Benchmark complete!")
        return 0
        
    finally:
        await native.close()
        await mcp.close()


if __name__ == "__main__":
    exit(asyncio.run(main()))
