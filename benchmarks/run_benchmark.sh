#!/bin/bash
# Run MCP vs Native Latency Benchmark
# Usage: ./run_benchmark.sh [iterations]

set -e

ITERATIONS=${1:-100}
WARMUP=${2:-10}

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

# Wait for services to be ready
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

MAX_WAIT=60
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    NATIVE_READY=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health 2>/dev/null || echo "000")
    MCP_READY=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/health 2>/dev/null || echo "000")
    
    if [ "$NATIVE_READY" = "200" ] && [ "$MCP_READY" = "200" ]; then
        echo "  ✅ Native API ready (port 8000)"
        echo "  ✅ MCP Server ready (port 8080)"
        break
    fi
    
    echo "  Waiting... (Native: $NATIVE_READY, MCP: $MCP_READY)"
    sleep 2
    WAITED=$((WAITED + 2))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "❌ Services failed to start within ${MAX_WAIT}s"
    echo ""
    echo "Native logs:"
    docker-compose -f docker-compose.mcp-benchmark.yml logs native-api --tail=20
    echo ""
    echo "MCP logs:"
    docker-compose -f docker-compose.mcp-benchmark.yml logs mcp-server --tail=20
    exit 1
fi

echo ""
echo "🔥 Running benchmark..."
echo ""

# Run benchmark
cd ..
uv run benchmarks/benchmark_latency.py \
    --iterations $ITERATIONS \
    --warmup $WARMUP \
    --output "benchmarks/results_$(date +%Y%m%d_%H%M%S).json"

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Benchmark Complete!"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "To clean up:"
echo "  docker-compose -f benchmarks/docker-compose.mcp-benchmark.yml down"
echo ""

# Ask if user wants to clean up
read -p "Clean up services now? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    docker-compose -f benchmarks/docker-compose.mcp-benchmark.yml down
    echo "✅ Services stopped"
fi
