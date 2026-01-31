#!/usr/bin/env python3
"""
ACTUAL MCP vs Native Function Latency Benchmark

This tests:
1. Native FastAPI endpoints (function calling)
2. MCP Server tool calls via SSE transport

Usage:
    uv run mcp_native_benchmark.py --iterations 10 --warmup 2
"""
import asyncio
import json
import time
import statistics
import sys
import argparse
from dataclasses import dataclass
from typing import List, Optional

import httpx


@dataclass
class BenchmarkResult:
    method: str  # 'native' or 'mcp'
    operation: str
    latency_ms: float
    success: bool
    error: Optional[str] = None


class NativeClient:
    """Native FastAPI client."""
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.base_url = base_url
    
    async def list_tickets(self) -> tuple[List[dict], float]:
        """List tickets via native API."""
        start = time.perf_counter()
        r = await self.client.get(f"{self.base_url}/tickets")
        latency = (time.perf_counter() - start) * 1000
        r.raise_for_status()
        return r.json(), latency
    
    async def sync_status(self) -> tuple[dict, float]:
        """Get sync status via native API."""
        start = time.perf_counter()
        r = await self.client.get(f"{self.base_url}/sync/status")
        latency = (time.perf_counter() - start) * 1000
        r.raise_for_status()
        return r.json(), latency
    
    async def close(self):
        await self.client.aclose()


class MCPClient:
    """MCP client using SSE transport."""
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.session_id: Optional[str] = None
        self.message_endpoint: Optional[str] = None
    
    async def initialize(self):
        """Initialize MCP session via SSE."""
        # Connect to SSE endpoint to get session
        async with self.client.stream("GET", f"{self.base_url}/sse") as response:
            async for line in response.aiter_lines():
                if line.startswith("event: endpoint"):
                    continue
                if line.startswith("data: "):
                    endpoint = line[6:]  # Remove "data: "
                    if "/messages/?session_id=" in endpoint:
                        self.message_endpoint = self.base_url + endpoint
                        # Extract session ID
                        self.session_id = endpoint.split("session_id=")[1]
                        break
        
        if not self.session_id:
            raise Exception("Failed to get MCP session")
        
        # Send initialize request
        init_response = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "benchmark", "version": "1.0.0"}
        })
        
        if "result" not in init_response:
            raise Exception(f"MCP initialize failed: {init_response}")
        
        # Send initialized notification
        await self._send_notification("notifications/initialized")
    
    async def _send_request(self, method: str, params: dict) -> dict:
        """Send JSON-RPC request."""
        request = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params
        }
        
        r = await self.client.post(
            self.message_endpoint,
            json=request,
            headers={"Content-Type": "application/json"}
        )
        r.raise_for_status()
        return r.json()
    
    async def _send_notification(self, method: str):
        """Send JSON-RPC notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method
        }
        
        r = await self.client.post(
            self.message_endpoint,
            json=notification,
            headers={"Content-Type": "application/json"}
        )
        r.raise_for_status()
    
    async def list_tables(self) -> tuple[List[dict], float]:
        """List tables via MCP (equivalent to getting tickets)."""
        start = time.perf_counter()
        
        result = await self._send_request("tools/call", {
            "name": "list_objects",
            "arguments": {"schema": "public", "type": "table"}
        })
        
        latency = (time.perf_counter() - start) * 1000
        
        # Extract result from MCP response
        if "result" in result and "content" in result["result"]:
            content = result["result"]["content"]
            if content and len(content) > 0:
                data = json.loads(content[0]["text"])
                return data, latency
        
        return [], latency
    
    async def execute_query(self) -> tuple[List[dict], float]:
        """Execute query via MCP."""
        start = time.perf_counter()
        
        result = await self._send_request("tools/call", {
            "name": "execute_sql",
            "arguments": {"query": "SELECT * FROM reservation_tickets LIMIT 10"}
        })
        
        latency = (time.perf_counter() - start) * 1000
        
        # Extract result from MCP response
        if "result" in result and "content" in result["result"]:
            content = result["result"]["content"]
            if content and len(content) > 0:
                data = json.loads(content[0]["text"])
                return data, latency
        
        return [], latency
    
    async def close(self):
        await self.client.aclose()


def print_stats(name: str, latencies: List[float]):
    """Print statistics."""
    if not latencies:
        print(f"{name}: No successful requests")
        return
    
    latencies.sort()
    n = len(latencies)
    
    print(f"\n{name}:")
    print(f"  Mean:   {statistics.mean(latencies):.2f} ms")
    print(f"  Median: {statistics.median(latencies):.2f} ms")
    print(f"  Min:    {min(latencies):.2f} ms")
    print(f"  Max:    {max(latencies):.2f} ms")
    print(f"  P95:    {latencies[int(n*0.95)]:.2f} ms")
    if n > 1:
        print(f"  Std:    {statistics.stdev(latencies):.2f} ms")


async def run_benchmark(client, method: str, operation: str, iterations: int, warmup: int):
    """Run benchmark for a client."""
    results = []
    
    # Warmup
    print(f"  Warming up {method}...")
    for _ in range(warmup):
        try:
            if operation == "list":
                if method == "native":
                    await client.list_tickets()
                else:
                    await client.list_tables()
            elif operation == "query":
                if method == "native":
                    await client.sync_status()
                else:
                    await client.execute_query()
        except Exception as e:
            print(f"    Warmup error: {e}")
    
    # Benchmark
    print(f"  Running {iterations} iterations...")
    for i in range(iterations):
        try:
            if operation == "list":
                if method == "native":
                    _, latency = await client.list_tickets()
                else:
                    _, latency = await client.list_tables()
            elif operation == "query":
                if method == "native":
                    _, latency = await client.sync_status()
                else:
                    _, latency = await client.execute_query()
            
            results.append(latency)
            
            if (i + 1) % 5 == 0:
                print(f"    {i + 1}/{iterations} complete")
                
        except Exception as e:
            print(f"    Error on iteration {i + 1}: {e}")
    
    return results


async def main():
    parser = argparse.ArgumentParser(description="MCP vs Native Latency Benchmark")
    parser.add_argument("--iterations", "-i", type=int, default=10)
    parser.add_argument("--warmup", "-w", type=int, default=2)
    args = parser.parse_args()
    
    print("=" * 70)
    print("🚀 MCP vs NATIVE FUNCTION LATENCY BENCHMARK")
    print("=" * 70)
    print(f"\nConfiguration:")
    print(f"  Iterations: {args.iterations}")
    print(f"  Warmup: {args.warmup}")
    
    # Create clients
    native = NativeClient()
    mcp = MCPClient()
    
    try:
        # Initialize MCP
        print("\n🔌 Initializing MCP session...")
        try:
            await mcp.initialize()
            print("  ✅ MCP connected")
        except Exception as e:
            print(f"  ❌ MCP failed: {e}")
            print("  Falling back to HTTP-only comparison")
            mcp = None
        
        # Benchmark 1: List operation
        print("\n📋 Benchmarking: List Tables/Tickets")
        print("-" * 70)
        
        native_latencies = await run_benchmark(
            native, "native", "list", args.iterations, args.warmup
        )
        print_stats("Native API", native_latencies)
        
        if mcp:
            mcp_latencies = await run_benchmark(
                mcp, "mcp", "list", args.iterations, args.warmup
            )
            print_stats("MCP", mcp_latencies)
        
        # Benchmark 2: Query operation
        print("\n📋 Benchmarking: Query/Status")
        print("-" * 70)
        
        native_latencies2 = await run_benchmark(
            native, "native", "query", args.iterations, args.warmup
        )
        print_stats("Native API", native_latencies2)
        
        if mcp:
            mcp_latencies2 = await run_benchmark(
                mcp, "mcp", "query", args.iterations, args.warmup
            )
            print_stats("MCP", mcp_latencies2)
        
        # Summary
        print("\n" + "=" * 70)
        print("📊 SUMMARY")
        print("=" * 70)
        
        if mcp and native_latencies and mcp_latencies:
            native_mean = statistics.mean(native_latencies)
            mcp_mean = statistics.mean(mcp_latencies)
            overhead = mcp_mean - native_mean
            
            print(f"\nList Operation:")
            print(f"  Native:     {native_mean:.2f} ms")
            print(f"  MCP:        {mcp_mean:.2f} ms")
            print(f"  Overhead:   +{overhead:.2f} ms ({overhead/native_mean*100:.0f}%)")
            print(f"  Slowdown:   {mcp_mean/native_mean:.1f}x")
            
            if overhead < 20:
                print(f"\n  ✅ MCP overhead is acceptable (<20ms)")
            elif overhead < 50:
                print(f"\n  ⚠️  MCP overhead is moderate (20-50ms)")
                print(f"     Consider for admin tools, not real-time voice")
            else:
                print(f"\n  ❌ MCP overhead is high (>50ms)")
                print(f"     Not recommended for voice AI")
        
        print("\n" + "=" * 70)
        
    finally:
        await native.close()
        if mcp:
            await mcp.close()


if __name__ == "__main__":
    asyncio.run(main())
