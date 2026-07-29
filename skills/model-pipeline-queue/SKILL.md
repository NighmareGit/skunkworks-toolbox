---
name: model-pipeline-queue
description: >
  Pipeline model calls (e.g. 9B → 35B) through a producer-consumer queue so
  the downstream model starts processing as soon as each upstream result
  arrives, instead of waiting for all upstream results to complete.
  Use when: "model pipeline", "producer consumer", "streaming LLM", "9B 35B",
  "pipeline model calls", "queue models", "/model-pipeline-queue".
metadata:
  short-description: "Producer-consumer queue for pipelining LLM model calls"
---

# Model Pipeline Queue

Pipeline two or more model stages through a producer-consumer queue. The
downstream model starts processing each result as soon as the upstream
produces it — instead of waiting for ALL upstream results to complete.

```
Time:    9B-A  9B-B  9B-C  9B-D  9B-E  ...
           │     │     │     │     │
Queue:     └──┬──┘     │     │     │
              │  ┌──────┘     │     │
              ▼  ▼            │     │
          35B-A  35B-B        │     │
                              ▼     ▼
                          35B-C  35B-D ...
```

Speedup for N tickers: from `N × (T9 + T35)` to `N × max(T9, T35)`.

## Inputs

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `tickers` | list[str] | required | All tickers to process |
| `producer_fn` | callable | required | Function(ticker) → result dict for upstream model |
| `consumer_fn` | callable | required | Function(ticker, producer_result) → result dict for downstream model |
| `n_workers_producer` | int | 4 | Concurrent producer workers |
| `n_workers_consumer` | int | 2 | Concurrent consumer workers |
| `timeout_per_call` | int | 60 | Timeout in seconds per model call |
| `error_mode` | string | `"continue"` | `"continue"` (log and skip) or `"fail_fast"` (raise) |
| `queue_maxsize` | int | 0 | Queue capacity (0 = unlimited) |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `producer_results` | dict[ticker, dict] | All producer outputs by ticker |
| `consumer_results` | dict[ticker, dict] | All consumer outputs by ticker |
| `n_producer_ok` | int | Successful producer calls |
| `n_producer_failed` | int | Failed producer calls |
| `n_consumer_ok` | int | Successful consumer calls |
| `n_consumer_failed` | int | Failed consumer calls |
| `errors` | list[dict] | Per-ticker error details |
| `total_time_s` | float | Wall-clock time for all stages |
| `speedup_vs_serial` | float | Estimated speedup factor |

## How to Use

### Core Pattern (concurrent.futures + queue.Queue)

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Thread
import time

def pipeline_models(tickers, producer_fn, consumer_fn,
                    n_workers_producer=4, n_workers_consumer=2,
                    timeout_per_call=60, error_mode="continue",
                    queue_maxsize=0):
    """Pipeline two model stages through a producer-consumer queue.
    
    Producer workers call producer_fn(ticker) and enqueue results.
    Consumer workers dequeue and call consumer_fn(ticker, producer_result).
    """
    queue = Queue(maxsize=queue_maxsize)
    producer_results = {}
    consumer_results = {}
    errors = []
    n_producer_ok = 0
    n_producer_failed = 0
    n_consumer_ok = 0
    n_consumer_failed = 0
    t0 = time.time()
    
    def _produce():
        """Run producer workers, enqueue each result as it completes."""
        with ThreadPoolExecutor(max_workers=n_workers_producer) as pool:
            futures = {pool.submit(producer_fn, t): t for t in tickers}
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    result = future.result(timeout=timeout_per_call)
                    producer_results[ticker] = result
                    nonlocal n_producer_ok
                    n_producer_ok += 1
                    queue.put((ticker, result))
                except Exception as e:
                    nonlocal n_producer_failed
                    n_producer_failed += 1
                    err = {"ticker": ticker, "stage": "producer", "error": str(e)}
                    errors.append(err)
                    if error_mode == "fail_fast":
                        raise
                    # Enqueue a sentinel so consumer still runs (degraded)
                    queue.put((ticker, None))
        # Signal consumers that production is done
        for _ in range(n_workers_consumer):
            queue.put(None)
    
    def _consume():
        """Run consumer workers, processing results from the queue."""
        with ThreadPoolExecutor(max_workers=n_workers_consumer) as pool:
            while True:
                item = queue.get()
                if item is None:
                    break  # production complete
                ticker, prod_result = item
                try:
                    future = pool.submit(consumer_fn, ticker, prod_result)
                    cons_result = future.result(timeout=timeout_per_call)
                    consumer_results[ticker] = cons_result
                    nonlocal n_consumer_ok
                    n_consumer_ok += 1
                except Exception as e:
                    nonlocal n_consumer_failed
                    n_consumer_failed += 1
                    err = {"ticker": ticker, "stage": "consumer", "error": str(e)}
                    errors.append(err)
                    if error_mode == "fail_fast":
                        raise
    
    # Start producer and consumer threads
    producer_thread = Thread(target=_produce, daemon=True)
    consumer_thread = Thread(target=_consume, daemon=True)
    producer_thread.start()
    consumer_thread.start()
    producer_thread.join()
    consumer_thread.join()
    
    elapsed = time.time() - t0
    serial_estimate = len(tickers) * 2 * 10  # rough: 10s per call, 2 stages
    speedup = serial_estimate / max(elapsed, 0.01) if elapsed > 0 else 0
    
    return {
        "producer_results": producer_results,
        "consumer_results": consumer_results,
        "n_producer_ok": n_producer_ok,
        "n_producer_failed": n_producer_failed,
        "n_consumer_ok": n_consumer_ok,
        "n_consumer_failed": n_consumer_failed,
        "errors": errors,
        "total_time_s": round(elapsed, 2),
        "speedup_vs_serial": round(speedup, 1),
    }
```

### Worked Example: 9B → 35B Pipeline

```python
# Define producers and consumers
def screen_with_9b(ticker):
    """Call 9B model to screen a ticker. Returns dict or raises."""
    resp = requests.post("http://endpoint:8080/v1/completions",
                         json={"ticker": ticker}, timeout=30)
    resp.raise_for_status()
    return resp.json()  # includes screening_verdict, direction, reasoning

def generate_context_with_35b(ticker, screening_result):
    """Call 35B model with screening context. Returns execution context or raises."""
    if screening_result is None:
        # Producer failed — call 35B with degraded context
        prompt = f"Ticker {ticker} has no screening data. Provide default execution context."
    else:
        prompt = f"Ticker {ticker}: {screening_result}. Provide execution context."
    resp = requests.post("http://endpoint:8083/v1/completions",
                         json={"prompt": prompt}, timeout=180)
    resp.raise_for_status()
    return resp.json()

# Run the pipeline
result = pipeline_models(
    tickers=["AAPL", "MSFT", "META", "NVDA", "GOOGL"],
    producer_fn=screen_with_9b,
    consumer_fn=generate_context_with_35b,
    n_workers_producer=6,   # 9B is fast
    n_workers_consumer=3,   # 35B is slower, fewer workers
    timeout_per_call=180,
)
print(f"Pipeline: {result['n_producer_ok']} screened, "
      f"{result['n_consumer_ok']} contextualized in "
      f"{result['total_time_s']}s ({result['speedup_vs_serial']}x vs serial)")
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Producer (9B) fails for a ticker | Consumer (35B) still runs with `producer_result=None` — degraded context |
| Consumer (35B) fails | Ticker skipped in final output, error logged |
| All producers fail | All consumers still attempt degraded-mode calls |
| `error_mode = fail_fast` | First failure in either stage raises immediately |
| Timeout exceeded | Per-call timeout raises `TimeoutError`, logged as failure |

## When to Use vs Alternatives

| Use this | If |
|----------|----|
| `model-pipeline-queue` | Two sequential model stages where downstream can start before upstream finishes |
| `concurrent.futures.as_completed()` directly | Simpler flow — produce all, then consume all (no pipelining needed) |
| ThreadPoolExecutor per stage | Stages have no data dependency between them |
| asyncio | All workers are async HTTP and you control the event loop |
| The `parallel-subprocess` skill | Pipelining subprocess calls, not model API calls |

## Integration with QuantRun Pipeline

To replace the sequential T1→T3→T4 flow in `run_live_pipeline.py`:

```python
from engines.stage_t1 import screen_one_ticker
from engines.stage_t4 import generate_one_context
from skills.model_pipeline_queue import pipeline_models

# Instead of:
#   for e in earnings: screen_one_ticker(e)  # sequential 9B
#   for e in earnings: validate(e)            # sequential T3
#   for e in earnings: generate_one_context(e)  # sequential 35B

# Do:
tickers = [e['ticker'] for e in earnings]
earnings_by_ticker = {e['ticker']: e for e in earnings}

result = pipeline_models(
    tickers=tickers,
    producer_fn=lambda t: screen_one_ticker(earnings_by_ticker[t]),
    consumer_fn=lambda t, scr: generate_one_context(
        ticker=t,
        screening=scr,
        price_data=price_by_ticker.get(t, []),
    ),
    n_workers_producer=6,
    n_workers_consumer=2,
)
```

Speedup: for 50 tickers with 9B=10s and 35B=20s per call:
- Serial: 50 × (10 + 20) = 1500s = **25 minutes**
- Pipelined: 50 × max(10, 20) = 1000s = **~17 minutes** (1.5x speedup)
- With optimal workers: bounded by the slower stage's throughput
