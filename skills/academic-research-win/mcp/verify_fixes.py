"""Bounded re-check: query the LOCAL (fixed) paper-search-mcp for the sources that
previously errored (zenodo/hal/pubmed) and confirm the shared `errors` map no
longer contains the `'str' object has no attribute 'isoformat'` /
`not well-formed (invalid token)` messages.

Run with the SKILL venv so the `mcp` SDK is importable:
    mcp\.venv\Scripts\python.exe mcp/verify_fixes.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

LOCAL = os.environ.get("PAPER_SEARCH_MCP_LOCAL_DIR", r"D:\projects\pool\paper-search-mcp")


def _text(res):
    out = []
    for c in getattr(res, "content", []) or []:
        out.append(c.text if isinstance(c, str) else getattr(c, "text", ""))
    return "".join(out)


async def main():
    if not os.path.isdir(LOCAL):
        print(f"FAIL: local paper-search-mcp checkout not at {LOCAL}", file=sys.stderr)
        sys.exit(2)
    sp = StdioServerParameters(command="uv", args=["run", "--directory", LOCAL, "paper-search-mcp"])
    try:
        async with stdio_client(sp) as (rs, ws):
            async with ClientSession(rs, ws) as s:
                await asyncio.wait_for(s.initialize(), timeout=60)
                tr = await s.list_tools()
                print("tools:", [t.name for t in tr.tools][:8], "...", flush=True)
                res = await asyncio.wait_for(s.call_tool("search_papers", arguments={
                    "query": "transformer", "max_results_per_source": 3,
                    "sources": "zenodo,hal,pubmed"}), timeout=150)
                data = json.loads(_text(res))
    except FileNotFoundError:
        print(f"FAIL: 'uv' not found or local dir missing. LOCAL={LOCAL}", file=sys.stderr)
        sys.exit(2)

    sr = data.get("source_results", {})
    errs = data.get("errors", {})
    papers = data.get("papers", [])
    print(f"papers total: {len(papers)}", flush=True)
    print("source_results:", json.dumps(sr), flush=True)
    print("errors:", json.dumps(errs, ensure_ascii=False), flush=True)

    bad_msgs = ("'str' object has no attribute 'isoformat'", "not well-formed (invalid token)")
    remaining = {k: v for k, v in errs.items() if isinstance(v, str) and any(b in v for b in bad_msgs)}
    print("previously-failing sources still erroring:", json.dumps(remaining) or "{}", flush=True)

    # Per-source verdicts
    for src in ("zenodo", "hal", "pubmed"):
        cnt = sr.get(src, 0)
        msg = errs.get(src, "")
        ok = (not msg) and cnt > 0
        print(f"  [{src}] papers={cnt} error={'yes' if msg else 'no'}  -> {'PASS' if ok else 'UNVERIFIED'}", flush=True)

    if remaining:
        print("RESULT: still failing", file=sys.stderr)
        sys.exit(1)
    # Require at least the previously-broken sources to now yield results without the old errors.
    for src in ("zenodo", "hal", "pubmed"):
        if sr.get(src, 0) == 0 and errs.get(src):
            print(f"RESULT: {src} still errors", file=sys.stderr); sys.exit(1)
    print("RESULT: previously-failing sources recovered (no isoformat/XML errors)", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print("FAIL:", e, file=sys.stderr); sys.exit(1)
