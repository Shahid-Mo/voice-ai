#!/bin/bash
# Run MCP vs Native Latency Benchmark
# Usage: ./run_benchmark.sh [iterations] [warmup]

set -e

ITERATIONS=${1:-10}
WARMUP=${2:-2}

echo "═══════════════════════════════════════════════════════════════"
echo "  MCP vs Native Function Latency Benchmark"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Configuration:"
echo "  Iterations: $ITERATIONS"
echo "  Warmup: $WARMUP"
echo ""

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found. Please install Docker Compose."
    exit 1
fi

# Start services
echo "🚀 Starting services..."
docker-compose -f docker-compose.mcp-benchmark.yml up -d

# Wait for services
echo ""
echo "⏳ Waiting for services (10s)..."
sleep 10

# Quick health check
echo ""
echo "🔍 Checking services..."
if curl -s --max-time 5 http://localhost:8000/health > /dev/null; then
    echo "  ✅ Native API ready (port 8000)"
else
    echo "  ❌ Native API not responding"
fi

if curl -s --max-time 5 http://localhost:8080/sse > /dev/null; then
    echo "  ✅ MCP Server ready (port 8080)"
else
    echo "  ⚠️  MCP Server not responding (may still work)"
fi

echo ""
echo "🔥 Running benchmark..."
echo ""

# Run the simple benchmark
cd ..
uv run benchmarks/simple_benchmark.py

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Benchmark Complete!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "To clean up:"
echo "  cd benchmarks && docker-compose -f docker-compose.mcp-benchmark.yml down"
echo ""

# Ask if user wants to clean up
read -p "Clean up services now? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    docker-compose -f docker-compose.mcp-benchmark.yml down
    echo "✅ Services stopped"
fi
