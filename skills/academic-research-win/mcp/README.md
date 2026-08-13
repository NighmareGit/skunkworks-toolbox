# MCP server registration (Windows, native / no Docker)

This skill is the **local Windows variant** — it is *not* intended for the public
sanitized `skunkworks-toolbox` mirror (local host paths + `$env:USERPROFILE` are
used by design here). Two MCP servers back `academic-research-win`:

| Server | Role in the workflow | Native Windows launch |
|--------|----------------------|------------------------|
| `paper-search-mcp` | Stage 2 search (22 sources) + Stage 4 Crossref metadata | `uvx paper-search-mcp` (or `pip install paper-search-mcp`, or `uv run --directory <local-checkout> paper-search-mcp`) |
| `academic-mcp` (vendored `academic_mcp.py`) | Stage 3 OpenAlex citation graph walk — paper-search-mcp has **no** equivalent | `python academic_mcp.py` from a small local venv |

Both are **stdio Python servers** — neither requires Docker or a container
runtime. That is the key Windows fact: you do **not** need Docker here.

## Install prerequisites (run once)

```powershell
# 1) paper-search-mcp (preferred: uvx keeps it isolated)
winget install --id Microsoft.Distribution.OpenSSH  # only if you lack uvx; skip otherwise
uv tool install uvx | Out-Null; uvx --version     # uvx is bundled with uv
uvx paper-search-mcp --help                        # smoke-test the console script

# 2) academic-mcp (vendored server file lives in skunkworks-toolbox; the venv
#    that RUNS it is created locally under THIS skill -> does not touch skunkworks)
$venv = "D:\projects\pool\skills\academic-research-win\mcp\.venv"
$ac   = "D:\projects\skunkworks-toolbox\skills\academic-research\server"
python -m venv $venv
& "$venv\Scripts\python.exe" -m pip install -r "$ac/requirements.txt"   # -> fastmcp, pulls mcp
& "$venv\Scripts\python.exe" "$ac/academic_mcp.py" --help 2>$null; Write-Host "academic-mcp runnable"
```

`paper-search-mcp` is fully keyless for most sources; set
`PAPER_SEARCH_MCP_UNPAYWALL_EMAIL` for the Unpaywall source (it requires an email
for its polite pool). The CORE / Semantic Scholar keys are optional.

## Register both servers in the agent runtime (~/.grok/mcpServers)

The runtime config is a JSON object mapping **server name → { command, args, env }**.
Use the server names exactly as qualified in the workflow (`paper-search-mcp__…`
and `academic-mcp__…`) — i.e. register them under keys `paper-search-mcp` and
`academic-mcp`.

`mcpServers.json` (drop-in for the `*.grok/mcpServers` store your runtime reads):

```jsonc
{
  "paper-search-mcp": {
    "command": "uvx",
    "args": ["paper-search-mcp"],
    "env": {
      "PAPER_SEARCH_MCP_UNPAYWALL_EMAIL": "you@example.org",
      "PAPER_SEARCH_MCP_CORE_API_KEY": "",            // optional, free
      "PAPER_SEARCH_MCP_SEMANTIC_SCHOLAR_API_KEY": "" // optional
    }
  },
  "academic-mcp": {
    "command": "D:\\projects\\pool\\skills\\academic-research-win\\mcp\\.venv\\Scripts\\python.exe",
    "args": ["D:\\projects\\skunkworks-toolbox\\skills\\academic-research\\server\\academic_mcp.py"],
    "env": {}
  }
}
```

> Prefer calling the venv `python.exe` **directly** (as above) instead of
> `.\.venv\Scripts\Activate.ps1 && python …`. MCP hosts spawn a single process;
> direct python invocation avoids shell-activation pitfalls on Windows.

## Automate it

`register-mcp-servers.ps1` sets up the `academic-mcp` venv if missing and writes
the JSON above to `$env:USERPROFILE\.grok\mcpServers.json`. Re-run it idempotently
after moving the toolbox or rotating your email.

## Local development checkout (optional)

To run/debug a **local** checkout of `paper-search-mcp` (e.g. a fork with
uncommitted fixes) instead of the `uvx` release, register it directly:

```powershell
powershell -ExecutionPolicy Bypass -File mcp/register-mcp-servers.ps1 -PaperSearchMcpLocalDir D:\projects\pool\paper-search-mcp
```

This writes a `paper-search-mcp` entry whose `command` is `uv` (args `run
--directory <dir> paper-search-mcp`) and sets `env.PAPER_SEARCH_MCP_LOCAL_DIR` so
downstream tooling can detect the local launch. The default (no flag) keeps
`uvx paper-search-mcp`, so the skill stays runnable for anyone without a checkout.

The live E2E honors the same override:

```powershell
$env:PAPER_SEARCH_MCP_LOCAL_DIR = "D:\projects\pool\paper-search-mcp"
mcp\.venv\Scripts\python.exe mcp\e2e_smoke.py
```

## Why two servers instead of replacing academic-mcp wholesale

`paper-search-mcp` covers search + full-text far better (22 sources, PDF download,
text extraction) and is actively maintained. But it has **no citation-graph walk**
— that single tool (`academic_citation_chain`) is the one capability no other MCP
exposes, and Stage 3 of this pipeline depends on it. The hybrid model therefore:
- uses `paper-search-mcp` for everything it can (search, abstract, metadata, PDF),
- keeps the existing `academic-mcp` stdio server **only** for Stage 3,
- requires no fork, no Docker, and no modification to `skunkworks-toolbox`.

## Failure modes

| Mode | Response |
|------|----------|
| `paper-search-mcp` not reachable | `search_tool`/`use_tool` fails → Stage 2 aborts; report "paper-search-mcp not registered in ~/.grok/mcpServers". |
| `academic-mcp` not reachable | Stage 2 proceeds (search is paper-search-mcp); Stage 3 aborts → cite chain skipped, mark coverage gap. |
| 429 / rate-limited source | paper-search-mcp returns per-source errors in its `errors` map; surface which source failed, suggest retry in 30s. |
| No results for query | "No academic results found for `<query>`" — do NOT fabricate. |
