---
name: parallel-subprocess
description: >
  Run N subprocess calls in parallel with configurable batch size, per-batch
  timeout, error handling, and result merging. Use when you need to parallelize
  any subprocess-based data fetch or computation — IBKR, options, sentiment,
  fundamentals, or any other tool that takes --tickers as input. Trigger
  phrases: "parallel subprocess", "concurrent fetch", "batch subprocess",
  "run tools in parallel", "/parallel-subprocess".
metadata:
  short-description: "Generic parallel subprocess executor with batching, timeout, and merge"
---

# Parallel Subprocess Executor

A generic pattern for running N subprocess calls in parallel, where each
call operates on a subset of tickers (a batch), and results are merged.

## Inputs

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command_template` | string | required | The tool command, e.g. `tools/fetch-ibkr-data/tool.py --tickers` |
| `tickers` | list[str] | required | All tickers to process |
| `batch_size` | int | 50 | Tickers per subprocess call |
| `per_batch_timeout` | int | 180 | Timeout in seconds per subprocess call |
| `max_workers` | int | 4 | Max concurrent subprocesses |
| `result_key` | string | `"data"` | Key in JSON output to extract results from |
| `merge_strategy` | string | `"extend"` | How to merge results: `"extend"` (list append) or `"update"` (dict merge) |
| `error_mode` | string | `"continue"` | `"continue"` (log and skip) or `"fail_fast"` (raise on first error) |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `results` | list or dict | Merged results from all successful batches |
| `n_success` | int | Number of successful batches |
| `n_failed` | int | Number of failed batches |
| `errors` | list[dict] | Per-batch error details |
| `total_time_s` | float | Wall-clock time for all batches |

## How to Use

### Step 1: Define your command

```python
import subprocess, json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_batch(batch_tickers, cmd_template, timeout, result_key):
    """Run one subprocess batch. Returns (batch_index, result_list_or_none, error_or_none)."""
    ticker_str = ','.join(batch_tickers)
    full_cmd = cmd_template + [ticker_str]
    try:
        sr = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
        if sr.returncode != 0:
            return batch_tickers, None, f"exit code {sr.returncode}: {sr.stderr[:200]}"
        data = json.loads(sr.stdout)
        items = data.get(result_key, []) if isinstance(data, dict) else data
        return batch_tickers, items, None
    except subprocess.TimeoutExpired:
        return batch_tickers, None, f"timeout after {timeout}s"
    except Exception as e:
        return batch_tickers, None, str(e)
```

### Step 2: Batch and dispatch

```python
def parallel_fetch(command_template, tickers, batch_size=50, per_batch_timeout=180,
                   max_workers=4, result_key="data", merge_strategy="extend",
                   error_mode="continue"):
    """Fetch data from all tickers in parallel batches."""
    batches = [tickers[i:i+batch_size] for i in range(0, len(tickers), batch_size)]
    n_batches = len(batches)
    
    all_results = [] if merge_strategy == "extend" else {}
    errors = []
    n_success = 0
    n_failed = 0
    t0 = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(run_batch, batch, command_template, per_batch_timeout, result_key): i
            for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            batch_tickers, items, error = future.result()
            if error:
                n_failed += 1
                errors.append({"batch_tickers": batch_tickers, "error": error})
                if error_mode == "fail_fast":
                    raise RuntimeError(f"Batch failed: {error}")
                else:
                    print(f"  [parallel-subprocess] batch failed: {error}", file=sys.stderr)
            else:
                n_success += 1
                if merge_strategy == "extend":
                    all_results.extend(items)
                elif merge_strategy == "update":
                    all_results.update(items)
    
    elapsed = time.time() - t0
    
    return {
        "results": all_results,
        "n_success": n_success,
        "n_failed": n_failed,
        "errors": errors,
        "total_time_s": round(elapsed, 2),
    }
```

### Step 3: Call it

```python
# Example: parallel IBKR data fetch
result = parallel_fetch(
    command_template=[sys.executable, "tools/fetch-ibkr-data/tool.py", "--tickers"],
    tickers=TICKERS,
    batch_size=50,
    per_batch_timeout=180,
    max_workers=4,
    result_key="data",
)
print(f"Fetched {len(result['results'])} rows in {result['total_time_s']}s "
      f"({result['n_success']}/{result['n_success']+result['n_failed']} batches)")
```

## Integration with Existing Code

To replace the sequential data fetch in `run_live_pipeline.py` (~lines 245-310):

1. Import this skill's pattern
2. Replace the sequential IBKR call:
   ```python
   # OLD:
   for batch in ticker_batches:
       sr = subprocess.run([...], timeout=120)
       ...
   # NEW:
   ibkr_result = parallel_fetch(
       [sys.executable, "tools/fetch-ibkr-data/tool.py", "--tickers"],
       TICKERS, batch_size=50, per_batch_timeout=180, max_workers=4,
   )
   for r in ibkr_result["results"]:
       price_by_ticker.setdefault(r["ticker"], []).append(r)
   ```

3. Do the same for options, sentiment, fundamentals, earnings history —
   each is just a `parallel_fetch()` call with different parameters

## Worked Example: IBKR + Options + Sentiment in Parallel

The real power comes from running ALL data sources concurrently:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=4) as pool:
    futures = {
        pool.submit(parallel_fetch,
            [sys.executable, "tools/fetch-ibkr-data/tool.py", "--tickers"],
            TICKERS, 50, 180, 4, "data"): "ibkr",
        pool.submit(parallel_fetch,
            [sys.executable, "tools/fetch-options-flow/tool.py", "--tickers"],
            TICKERS, 25, 180, 4, "data"): "options",
        pool.submit(parallel_fetch,
            [sys.executable, "tools/fetch-sentiment/tool.py", "--tickers"],
            TICKERS, 50, 180, 4, "data"): "sentiment",
        pool.submit(parallel_fetch,
            [sys.executable, "tools/fetch-fundamentals/tool.py", "--tickers"],
            TICKERS, 50, 180, 4, "data"): "fundamentals",
    }
    data_sources = {}
    for future in as_completed(futures):
        name = futures[future]
        try:
            data_sources[name] = future.result()
            print(f"  {name}: {len(data_sources[name]['results'])} rows "
                  f"({data_sources[name]['total_time_s']}s)")
        except Exception as e:
            print(f"  {name}: FAILED - {e}")
            data_sources[name] = {"results": [], "errors": [str(e)]}
```

This runs IBKR, options, sentiment, and fundamentals CONCURRENTLY,
completing in ~max(IBKR_time, options_time, ...) instead of sum(...).

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Batch times out | Logged as error, other batches continue |
| Subprocess returns non-zero | Logged with stderr snippet, other batches continue |
| JSON parse fails | Logged, batch skipped |
| All batches fail | Returns empty results with all errors listed |
| `error_mode = fail_fast` | First failure raises immediately |

## When to Use vs Alternatives

| Use this | If |
|----------|----|
| `parallel-fetch` | Multiple independent subprocess calls on different data slices |
| ThreadPoolExecutor directly | Tasks are lightweight and don't involve subprocess |
| asyncio | Tasks are HTTP requests without subprocess overhead |
| multiprocessing | Tasks are CPU-bound computation (not I/O-bound subprocess) |
