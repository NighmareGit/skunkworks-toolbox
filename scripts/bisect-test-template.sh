#!/bin/bash
# Returns 0 if GDN produces text (GOOD), 1 if garbled (BAD), 125 if build/setup fails
set -e

MODEL="${MODEL_PATH:?set MODEL_PATH to your model .gguf}"
BUILD_DIR="${BUILD_DIR:?set BUILD_DIR to your llama.cpp build}"
PORT=$((19950 + RANDOM % 1000))

# Kill ALL llama-server instances
pkill -f "llama-server" 2>/dev/null || true
sleep 2
fuser -k $PORT/tcp 2>/dev/null || true
sleep 1

# Force cmake reconfigure + clean rebuild of server binary
cd "$BUILD_DIR"
rm -f bin/llama-server
if ! cmake .. -DGGML_HIPBLAS=ON -DGGML_HIP_UMA=ON -DCMAKE_HIP_ARCHITECTURES=gfx1100 > /tmp/bisect-cmake.log 2>&1; then
    echo "CMAKE RECONFIGURE FAILED"
    exit 125
fi
if ! cmake --build . --target llama-server -j$(nproc) > /tmp/bisect-build.log 2>&1; then
    echo "BUILD FAILED"
    exit 125
fi

# Start server
HIP_VISIBLE_DEVICES=0 ./bin/llama-server \
    -m "$MODEL" -ngl 99 --no-mmap -t 4 --port $PORT \
    > /tmp/bisect-server.log 2>&1 &
SERVER_PID=$!
sleep 8

# Check server is alive
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "SERVER DIED"
    exit 125
fi

# Test
RESPONSE=$(curl -s --max-time 45 "http://localhost:$PORT/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"messages":[{"role":"user","content":"Hi"}],"max_tokens":8,"temperature":0}' 2>/dev/null)

# Cleanup server
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true
sleep 2
pkill -f "llama-server" 2>/dev/null || true
sleep 1

# Check: does response contain alphabetic text in reasoning_content or content?
echo "$RESPONSE" > /tmp/bisect-response.json
HAS_ALPHA=$(python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    msg = d['choices'][0]['message']
    text = msg.get('reasoning_content', '') or msg.get('content', '')
    if any(c.isalpha() for c in text):
        sys.exit(0)
    else:
        sys.exit(1)
except Exception as e:
    print(f'PARSE ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" < /tmp/bisect-response.json 2>/tmp/bisect-python-err.log && echo "GOOD" || echo "BAD")

echo "=== RESULT: $HAS_ALPHA ==="
echo "=== Response preview: $(head -c 200 /tmp/bisect-response.json) ==="
if [ "$HAS_ALPHA" = "GOOD" ]; then
    echo "GOOD: GDN produces text on GPU"
    exit 0
else
    echo "BAD: GDN garbled on GPU"
    exit 1
fi
