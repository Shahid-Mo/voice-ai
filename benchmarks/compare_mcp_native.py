#!/usr/bin/env python3
"""
MCP vs Native - ACTUAL Comparison

Tests the SAME operation through both:
1. Native FastAPI endpoint (direct HTTP)
2. MCP tool call (JSON-RPC over SSE)

Both execute SQL query against the database.
"""
import asyncio
import json
import time
import statistics
import argparse
from dataclasses import dataclass
from typing import List, Optional, Tuple
import httpx


@dataclass
class Result:
    method: str
    latency_ms: float
    success: bool
    error: Optional[str] = None


async def test_native_api(iterations: int = 10, warmup: int = 2) -> List[Result]:
    """Test native FastAPI - GET /tickets endpoint."""
    print("\n🌐 Testing NATIVE API (FastAPI)")
    print("-" * 50)
    
    async with httpx.AsyncClient() as client:
        results = []
        
        # Warmup
        for _ in range(warmup):
            await client.get("http://localhost:8000/tickets")
        
        # Test
        for i in range(iterations):
            start = time.perf_counter()
            try:
                r = await client.get("http://localhost:8000/tickets")
                r.raise_for_status()
                latency = (time.perf_counter() - start) * 1000
                results.append(Result("native", latency, True))
            except Exception as e:
                latency = (time.perf_counter() - start) * 1000
                results.append(Result("native", latency, False, str(e)))
            
            if (i + 1) % 5 == 0:
                print(f"  {i + 1}/{iterations} done")
    
    return results


async def test_mcp(iterations: int = 10, warmup: int = 2) -> List[Result]:
    """Test MCP - Call execute_sql tool via SSE transport."""
    print("\n🔌 Testing MCP (Model Context Protocol)")
    print("-" * 50)
    
    results = []
    
    async with httpx.AsyncClient() as client:
        # Step 1: Connect to SSE and get session
        print("  Connecting to SSE...")
        
        session_id = None
        message_url = None
        
        try:
            async with client.stream("GET", "http://localhost:8080/sse", timeout=10.0) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        endpoint = line[6:]
                        if "session_id=" in endpoint:
                            message_url = f"http://localhost:8080{endpoint}"
                            session_id = endpoint.split("session_id=")[1]
                            print(f"  ✅ Session: {session_id[:8]}...")
                            break
        except Exception as e:
            print(f"  ❌ SSE connection failed: {e}")
            return []
        
        if not session_id:
            print("  ❌ No session ID received")
            return []
        
        # Step 2: Initialize
        print("  Initializing...")
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "benchmark", "version": "1.0"}
            }
        }
        
        try:
            r = await client.post(message_url, json=init_req)
            init_res = r.json()
            if "error" in init_res:
                print(f"  ❌ Initialize failed: {init_res['error']}")
                return []
        except Exception as e:
            print(f"  ❌ Initialize error: {e}")
            return []
        
        # Step 3: Send initialized notification
        await client.post(message_url, json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })
        
        print("  ✅ MCP ready")
        
        # Warmup
        print("  Warming up...")
        for _ in range(warmup):
            await client.post(message_url, json={
                "jsonrpc": "2.0",
                "id": int(time.time() * 1000),
                "method": "tools/call",
                "params": {
                    "name": "execute_sql",
                    "arguments": {"query": "SELECT * FROM reservation_tickets LIMIT 10"}
                }
            })
        
        # Test
        print(f"  Running {iterations} iterations...")
        for i in range(iterations):
            start = time.perf_counter()
            try:
                r = await client.post(message_url, json={
                    "jsonrpc": "2.0",
                    "id": int(time.time() * 1000),
                    "method": "tools/call",
                    "params": {
                        "name": "execute_sql",
                        "arguments": {"query": "SELECT * FROM reservation_tickets LIMIT 10"}
                    }
                })
                r.raise_for_status()
                response = r.json()
                
                if "error" in response:
                    latency = (time.perf_counter() - start) * 1000
                    results.append(Result("mcp", latency, False, response["error"].get("message")))
                else:
                    latency = (time.perf_counter() - start) * 1000
                    results.append(Result("mcp", latency, True))
                    
            except Exception as e:
                latency = (time.perf_counter() - start) * 1000
                results.append(Result("mcp", latency, False, str(e)))
            
            if (i + 1) % 5 == 0:
                print(f"  {i + 1}/{iterations} done")
    
    return results


def print_stats(name: str, results: List[Result]):
    """Print latency statistics."""
    latencies = [r.latency_ms for r in results if r.success]
    
    if not latencies:
        print(f"\n{name}: No successful results")
        return
    
    latencies.sort()
    n = len(latencies)
    
    print(f"\n{name}:")
    print(f"  Count:  {n}/{len(results)} successful")
    print(f"  Mean:   {statistics.mean(latencies):.2f} ms")
    print(f"  Median: {statistics.median(latencies):.2f} ms")
    print(f"  Min:    {min(latencies):.2f} ms")
    print(f"  Max:    {max(latencies):.2f} ms")
    print(f"  P95:    {latencies[int(n*0.95)]:.2f} ms")
    if n > 1:
        print(f"  Std:    {statistics.stdev(latencies):.2f} ms")


def print_comparison(native_results: List[Result], mcp_results: List[Result]):
    """Print side-by-side comparison."""
    native_latencies = [r.latency_ms for r in native_results if r.success]
    mcp_latencies = [r.latency_ms for r in mcp_results if r.success]
    
    if not native_latencies or not mcp_latencies:
        print("\n⚠️  Insufficient data for comparison")
        return
    
    native_mean = statistics.mean(native_latencies)
    mcp_mean = statistics.mean(mcp_latencies)
    overhead = mcp_mean - native_mean
    
    print("\n" + "=" * 60)
    print("📊 COMPARISON: MCP vs Native")
    print("=" * 60)
    
    print(f"\n{'Metric':<15} {'Native':>12} {'MCP':>12} {'Overhead':>15}")
    print("-" * 60)
    
    metrics = [
        ("Mean", native_mean, mcp_mean),
        ("Median", statistics.median(native_latencies), statistics.median(mcp_latencies)),
        ("Min", min(native_latencies), min(mcp_latencies)),
        ("Max", max(native_latencies), max(mcp_latencies)),
    ]
    
    for name, native_val, mcp_val in metrics:
        diff = mcp_val - native_val
        print(f"{name:<15} {native_val:>10.2f}ms {mcp_val:>10.2f}ms {diff:>+12.2f}ms")
    
    print("\n" + "=" * 60)
    print(f"MCP Overhead: +{overhead:.2f} ms ({overhead/native_mean*100:.0f}%)")
    print(f"MCP is {mcp_mean/native_mean:.1f}x slower than Native")
    
    # Recommendation
    print("\n📋 RECOMMENDATION:")
    if overhead < 10:
        print("  ✅ MCP overhead is minimal (<10ms)")
        print("     Either protocol works for Voice AI")
    elif overhead < 30:
        print("  ⚠️  MCP overhead is moderate (10-30ms)")
        print("     Borderline for real-time voice AI")
        print("     Use Native for voice, MCP for admin")
    else:
        print("  ❌ MCP overhead is significant (>30ms)")
        print("     Not recommended for real-time voice AI")
        print("     Use MCP only for non-latency-critical tools")
    
    # Voice AI context
    print("\n🎙️  VOICE AI CONTEXT:")
    voice_budget = 100  # ms budget for tool call in voice AI
    native_ok = native_mean < voice_budget
    mcp_ok = mcp_mean < voice_budget
    
    print(f"  Native: {native_mean:.1f}ms {'✅' if native_ok else '⚠️'}")
    print(f"  MCP:    {mcp_mean:.1f}ms {'✅' if mcp_ok else '❌'}")
    
    print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description="MCP vs Native Latency Benchmark")
    parser.add_argument("--iterations", "-i", type=int, default=10, help="Iterations (default: 10)")
    parser.add_argument("--warmup", "-w", type=int, default=2, help="Warmup runs (default: 2)")
    parser.add_argument("--native-only", action="store_true", help="Test only native API")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🚀 MCP vs NATIVE FUNCTION LATENCY BENCHMARK")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Iterations: {args.iterations}")
    print(f"  Warmup: {args.warmup}")
    print(f"\nTesting: SQL query execution")
    print("  - Native: GET /tickets endpoint")
    print("  - MCP: execute_sql tool via JSON-RPC")
    print()
    
    # Test Native
    native_results = await test_native_api(args.iterations, args.warmup)
    print_stats("NATIVE API", native_results)
    
    # Test MCP
    if not args.native_only:
        mcp_results = await test_mcp(args.iterations, args.warmup)
        print_stats("MCP", mcp_results)
        
        # Comparison
        if mcp_results:
            print_comparison(native_results, mcp_results)
    
    print("\n✅ Benchmark complete!")


if __name__ == "__main__":
    asyncio.run(main())
