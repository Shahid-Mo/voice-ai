#!/usr/bin/env python3
"""
Simple latency benchmark - Native API vs direct SQL (simulating MCP overhead)

Usage:
    uv run simple_benchmark.py
"""
import asyncio
import time
import statistics
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Database URL (from docker-compose)
DATABASE_URL = "postgresql+asyncpg://lotus:lotus@localhost:5432/blacklotus"

# API URLs
NATIVE_URL = "http://localhost:8000"


async def benchmark_native_list_tickets(iterations=10):
    """Benchmark native API list tickets endpoint."""
    async with httpx.AsyncClient() as client:
        latencies = []
        
        # Warmup
        for _ in range(2):
            await client.get(f"{NATIVE_URL}/tickets")
        
        # Benchmark
        for _ in range(iterations):
            start = time.perf_counter()
            r = await client.get(f"{NATIVE_URL}/tickets")
            latency = (time.perf_counter() - start) * 1000
            if r.status_code == 200:
                latencies.append(latency)
        
        return latencies


async def benchmark_direct_sql(iterations=10):
    """Benchmark direct SQL query (simulating what MCP does internally)."""
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    latencies = []
    
    async with async_session() as session:
        # Warmup
        for _ in range(2):
            from sqlalchemy import text
            await session.execute(text("SELECT * FROM reservation_tickets LIMIT 10"))
        
        # Benchmark
        for _ in range(iterations):
            from sqlalchemy import text
            start = time.perf_counter()
            result = await session.execute(text("SELECT * FROM reservation_tickets LIMIT 10"))
            rows = result.fetchall()
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)
    
    await engine.dispose()
    return latencies


def print_stats(name, latencies):
    """Print latency statistics."""
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
    print(f"  Std:    {statistics.stdev(latencies):.2f} ms")


async def main():
    print("=" * 60)
    print("SIMPLE LATENCY BENCHMARK")
    print("=" * 60)
    print("\nConfiguration:")
    print("  Iterations: 10")
    print("  Warmup: 2")
    
    # Test native API
    print("\n🔥 Benchmarking Native API...")
    native_latencies = await benchmark_native_list_tickets(10)
    print_stats("Native API", native_latencies)
    
    # Test direct SQL
    print("\n🔥 Benchmarking Direct SQL (baseline)...")
    sql_latencies = await benchmark_direct_sql(10)
    print_stats("Direct SQL", sql_latencies)
    
    # Calculate overhead
    if native_latencies and sql_latencies:
        native_mean = statistics.mean(native_latencies)
        sql_mean = statistics.mean(sql_latencies)
        http_overhead = native_mean - sql_mean
        
        print("\n" + "=" * 60)
        print("ANALYSIS")
        print("=" * 60)
        print(f"\nHTTP/API Overhead: {http_overhead:.2f} ms")
        print(f"Native API is {native_mean/sql_mean:.1f}x slower than direct SQL")
        print("\nNote: MCP would add additional ~20-40ms overhead on top of HTTP")
        print("      for JSON-RPC encoding, tool dispatch, and protocol handling.")
    
    print("\n✅ Benchmark complete!")


if __name__ == "__main__":
    asyncio.run(main())
