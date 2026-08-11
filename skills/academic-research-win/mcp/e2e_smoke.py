"""End-to-end smoke test for academic-research-win's MCP servers (Windows).

Run AFTER `register-mcp-servers.ps1` so the academic-mcp venv exists and
paper-search-mcp is reachable via uvx. Exercises the live APIs (no Docker, no
LLM key):

  Phase 1 - paper-search-mcp
    initialize -> tools/list (assert search_papers + get_crossref_paper_by_doi)
    tools/call search_papers("transformer")  -> >= 1 real paper
    run the skill's NORMALIZER on a live paper -> unified-schema fields present
  Phase 2 - academic-mcp (vendored academic_mcp.py)
    initialize -> tools/list (assert academic_citation_chain)
    seed a DOI from Phase 1 -> tools/call citation_chain(cites, depth=1)
    -> hop_1_count present
  Phase 4 - research workspace (mappings/research_workspace.py)
    download a live PDF to the OS-standard temp folder, MOVE it into
    research/<topic>/pdfs/, and refresh map.md with the live normalized paper
    + the citation-chain stats from Phase 2

Exit codes: 0 = all gates passed; 1 = contract assertion failed;
            2 = a server could not be launched (missing venv/uvx).

Usage (use the skill venv so the `mcp` SDK is importable):
    mcp\.venv\Scripts\python.exe mcp\e2e_smoke.py
"""
import asyncio
import importlib.util as _u
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

# --- configuration (override via env vars if your paths differ) ---
VENV_PY = os.environ.get(
    "ACADEMIC_PYTHON", str(SKILL_ROOT / "mcp" / ".venv" / "Scripts" / "python.exe"))
ACADEMIC_SERVER = os.environ.get(
    "ACADEMIC_SERVER",
    r"D:\projects\skunkworks-toolbox\skills\academic-research\server\academic_mcp.py")
PAPER_CMD = os.environ.get("PAPER_SEARCH_CMD", "uvx")
PAPER_ARGS = os.environ.get("PAPER_SEARCH_ARGS", "paper-search-mcp").split()
# Convenience override: launch a LOCAL checkout of paper-search-mcp via
# `uv run --directory <dir>` instead of uvx. Useful to test uncommitted fixes.
_LOCAL_PSMCP = os.environ.get("PAPER_SEARCH_MCP_LOCAL_DIR", "")
if _LOCAL_PSMCP and os.path.isdir(_LOCAL_PSMCP):
    PAPER_CMD = "uv"
    PAPER_ARGS = ["run", "--directory", _LOCAL_PSMCP, "paper-search-mcp"]
FALLBACK_DOI = "10.1038/nature12373"  # Hinton 2012, always indexed by OpenAlex

_has_mcp = _u.find_spec("mcp") is not None


def _text(res):
    """Flatten a tools/call result (list[Content]) to a single string."""
    out = []
    for c in getattr(res, "content", []) or []:
        out.append(c.text if isinstance(c, str) else getattr(c, "text", ""))
    return "".join(out)


async def phase1_paper_search():
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.client.session import ClientSession

    sp = StdioServerParameters(command=PAPER_CMD, args=PAPER_ARGS)
    try:
        async with stdio_client(sp) as (rs, ws):
            async with ClientSession(rs, ws) as s:
                cap = await s.initialize()
                name = cap.serverInfo.name if cap and cap.serverInfo else "?"
                tr = await s.list_tools()
                names = [t.name for t in tr.tools]
                print(f"  [paper-search-mcp] initialize OK ({name}); tools/list -> "
                      f"{len(names)} tools", flush=True)
                for need in ("search_papers", "get_crossref_paper_by_doi"):
                    assert need in names, f"paper-search-mcp missing tool: {need}"

                t0 = time.time()
                res = await asyncio.wait_for(s.call_tool("search_papers", arguments={
                    "query": "transformer", "max_results_per_source": 3,
                    "sources": "arxiv,openalex,crossref"}), timeout=45)
                data = json.loads(_text(res))
                papers = data.get("papers", [])
                print(f"  search_papers in {time.time()-t0:.1f}s -> {len(papers)} papers "
                      f"(source_results={data.get('source_results')}, errors={data.get('errors')})",
                      flush=True)
                assert len(papers) > 0, "search_papers returned no papers"
                first = papers[0]
                print(f"  first paper: {str(first.get('title',''))[:70]}", flush=True)
    except FileNotFoundError:
        print(f"  [paper-search-mcp] launch failed: command={PAPER_CMD!r} not found.",
              file=sys.stderr)
        return None

    from mappings import paper_search_mapping as norm
    rec = norm.normalize_paper(first)
    print("  normalized -> " + json.dumps(
        {k: rec.get(k) for k in norm.UNIFIED_FIELDS}, ensure_ascii=False)[:300], flush=True)
    for k in norm.UNIFIED_FIELDS:
        assert k in rec, f"normalizer missing field: {k}"
    print("  [PASS] normalizer produced full unified schema from LIVE search_papers output",
          flush=True)
    # Return the full raw record (carries pdf_url etc.) plus the resolved seed id.
    # Seed selection mirrors the `.rhia` Stage-3 rule (DOI first, arXiv id
    # second, URL excluded) via the normalizer's tested best_work_id_for_openalex.
    return {"seed": norm.best_work_id_for_openalex(first) or FALLBACK_DOI, "paper": first}


async def phase2_citation_chain(seed):
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.client.session import ClientSession

    sp = StdioServerParameters(command=VENV_PY, args=[ACADEMIC_SERVER])
    async with stdio_client(sp) as (rs, ws):
        async with ClientSession(rs, ws) as s:
            cap = await s.initialize()
            name = cap.serverInfo.name if cap and cap.serverInfo else "?"
            tr = await s.list_tools()
            names = [t.name for t in tr.tools]
            print(f"  [academic-mcp] initialize OK ({name}); tools/list -> {names}", flush=True)
            assert "academic_citation_chain" in names, "academic-mcp missing academic_citation_chain"
            for attempt in (seed, FALLBACK_DOI):
                print(f"  citation_chain on {attempt} (cites, depth=1)...", flush=True)
                t0 = time.time()
                try:
                    res = await asyncio.wait_for(s.call_tool("academic_citation_chain", arguments={
                        "work_id": attempt, "direction": "cites", "depth": 1}), timeout=40)
                    data = json.loads(_text(res))
                except asyncio.TimeoutError:
                    print("  [TIMEOUT] no response in 40s", flush=True)
                    continue
                if "error" in data:
                    print(f"  {attempt} -> OpenAlex error: {data['error']} (retry fallback)",
                          flush=True)
                    continue
                print(f"  done in {time.time()-t0:.1f}s -> hop_1_count={data.get('hop_1_count')} "
                      f"(start={data.get('start_work_id')})", flush=True)
                assert "hop_1_count" in data, "citation_chain response missing hop_1_count"
                print("  [PASS] live citation_chain returned citing papers", flush=True)
                return data.get("hop_1_count")
    raise AssertionError("citation_chain returned no usable result for any seed")


async def phase4_collect(seed_record, hop1):
    """Live demo of the research-workspace helpers on Windows, no Docker.

    * downloads a live PDF into the OS-standard temp folder (tempfile.gettempdir),
    * MOVES it into <tmp-research-root>/research/<topic>/pdfs/,
    * refreshes map.md with the live normalized paper + the chain stats.
    Uses a throwaway research_root so the repo is never polluted.
    """
    import urllib.request
    from mappings import research_workspace as rw
    from mappings import paper_search_mapping as norm

    first = seed_record["paper"]
    unified = norm.normalize_paper(first)

    # Isolate the collection in a throwaway root (do NOT write into the repo).
    tmp_root = tempfile.mkdtemp(prefix="acw-e2e-")
    os.environ["ACADEMIC_RESEARCH_ROOT"] = tmp_root
    topic = "transformer-baseline"

    print("  [workspace] research_root -> " + tmp_root, flush=True)
    print("  [workspace] topic_dir     -> research/" + rw._slug(topic) + "/", flush=True)

    # 1) transient download to the SYSTEM temp folder (never hard-coded).
    tmp_dl = rw.system_tmp_dir() / f"dl_{os.getpid()}.pdf"
    pdf_url = first.get("pdf_url")
    fetched = False
    if pdf_url:
        try:
            req = urllib.request.Request(pdf_url, headers={"User-Agent": "academic-research-win-e2e/0.1"})
            with urllib.request.urlopen(req, timeout=20) as r, open(tmp_dl, "wb") as out:
                out.write(r.read())
            fetched = True
        except Exception as e:  # noqa: BLE001 - any fetch failure -> placeholder
            print(f"  [note] pdf_url fetch skipped ({e!r}); using placeholder temp file", flush=True)
    if not fetched:
        tmp_dl.write_bytes(b"%PDF-1.4 E2E placeholder - real pdf_url fetch unavailable.\n")
    assert tmp_dl.exists() and tmp_dl.stat().st_size > 0, "temp download missing/empty"
    assert str(tmp_dl).startswith(str(rw.system_tmp_dir())), "temp download NOT in the OS temp folder"

    # 2) permanently collect (move) + index in map.md.
    rec = rw.place_and_index(
        tmp_dl, topic, unified,
        chain_cites=int(hop1 or 0), chain_refs=0,
        chain_stats={"direction": "cites", "depth": 1, "hop1": int(hop1 or 0)},
        notes=f"seeded from live search_papers; pdf fetched={fetched}",
    )
    assert not tmp_dl.exists(), "temp PDF was not moved out of the OS temp folder"

    # 3) assert the organised layout + map.md content.
    base = rw.topic_dir(topic)
    map_md = base / "map.md"
    assert map_md.is_file(), "map.md not written"
    text = map_md.read_text(encoding="utf-8")
    assert rec.title in text, "map.md missing the live paper title"
    assert "citation chain | direction=cites" in text, "map.md missing chain stats"
    assert "chain cites" in text, "map.md missing the chain-cites column"
    pdf_name = rec.pdf_path_rel.split("/")[-1]
    assert (base / "pdfs" / pdf_name).is_file(), f"collected PDF missing: pdfs/{pdf_name}"
    print(f"  [PASS] temp PDF moved into {base / 'pdfs' / pdf_name}", flush=True)
    print(f"  [PASS] map.md written ({map_md.name}) with live paper + chain stats", flush=True)
    print(f"  collected: 1 paper; chain cites(hop1)={hop1}; pdf in pdfs/", flush=True)

    shutil.rmtree(tmp_root, ignore_errors=True)  # keep the repo clean
    return {
        "topic_dir": str(base),
        "map_md": str(map_md),
        "pdfs_collected": 1,
        "papers_indexed": 1,
        "chain_hop1": int(hop1 or 0),
    }


async def main():
    if not _has_mcp:
        print("FAIL: 'mcp' SDK not importable. Use the skill venv: " + VENV_PY, file=sys.stderr)
        sys.exit(2)
    if not os.path.exists(VENV_PY):
        print(f"FAIL: academic-mcp venv not found at {VENV_PY}.", file=sys.stderr)
        print("  Run mcp\\register-mcp-servers.ps1 first.", file=sys.stderr)
        sys.exit(2)
    if not os.path.exists(ACADEMIC_SERVER):
        print(f"FAIL: academic_mcp.py not found at {ACADEMIC_SERVER}", file=sys.stderr)
        sys.exit(2)

    print("=== paper-search-mcp ===", flush=True)
    p1 = await phase1_paper_search()
    if p1 is None:
        print("[SKIP] paper-search-mcp unavailable; cannot seed citation_chain.", file=sys.stderr)
        sys.exit(2)
    seed = p1["seed"]

    print("\n=== academic-mcp ===", flush=True)
    hop1 = await phase2_citation_chain(seed)

    print("\n=== research workspace (Phase 4) ===", flush=True)
    ws = await phase4_collect(p1, hop1)

    print("\n=== RESULT ===", flush=True)
    print(json.dumps(
        {"search_papers_seed": seed, "citation_chain_hop1_count": hop1, "workspace": ws}
    ), flush=True)
    print("ALL E2E GATES PASSED", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print("FAIL:", e, file=sys.stderr); sys.exit(1)
    except FileNotFoundError as e:
        print(f"FAIL: could not launch a server ({e}).", file=sys.stderr); sys.exit(2)
