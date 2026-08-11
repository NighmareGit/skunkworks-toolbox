<#
.SYNOPSIS
    Registers the two MCP servers that power academic-research-win on Windows,
    natively (no Docker). Creates/uses a self-contained venv UNDER THIS SKILL
    (mcp\.venv) for the vendored academic-mcp server, and writes the agent-runtime
    mcpServers JSON. The academic-mcp server FILE itself stays in
    skunkworks-toolbox (read-only); only the venv is created locally.

.NOTES
    This is a LOCAL Windows variant -- it uses real host paths by design.
    Re-run idempotently after moving repos or rotating your email.

    Pass -PaperSearchMcpLocalDir <path> to launch paper-search-mcp from a LOCAL
    checkout (e.g. <paper-search-mcp-dir>) instead of `uvx`:
        powershell -ExecutionPolicy Bypass -File mcp/register-mcp-servers.ps1 -PaperSearchMcpLocalDir <paper-search-mcp-dir>
    The default (no flag) ships `uvx paper-search-mcp` so the skill works for
    anyone without a local checkout.
#>
param(
    [string]$AcademicServerDir = '<academic-research-server-dir>',
    [string]$VenvDir = "$PSScriptRoot\.venv",
    [string]$GrokDir = "$env:USERPROFILE\.grok",
    [string]$ConfigPath = "$env:USERPROFILE\.grok\mcpServers.json",
    [string]$UnpaywallEmail = 'you@example.org',
    [string]$PaperSearchMcpLocalDir = ''
)

$ErrorActionPreference = 'Stop'
Write-Host "== academic-research-win: MCP server registration =="

# --- 1. Ensure the academic-mcp venv exists + deps installed (fastmcp -> pulls mcp) ---
$venvPython = Join-Path $VenvDir 'Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating venv under $VenvDir"
    & python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}
$req = Join-Path $AcademicServerDir 'requirements.txt'
if (Test-Path $req) {
    Write-Host "Installing academic-mcp deps (fastmcp -> pulls mcp)"
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r $req
    if ($LASTEXITCODE -ne 0) { throw 'academic-mcp pip install failed' }
} else {
    Write-Host "No requirements.txt found; installing fastmcp directly"
    & $venvPython -m pip install 'fastmcp>=3.0'
    if ($LASTEXITCODE -ne 0) { throw 'academic-mcp pip install failed' }
}
$serverPy = Join-Path $AcademicServerDir 'academic_mcp.py'
if (-not (Test-Path $serverPy)) {
    throw "academic_mcp.py not found under $AcademicServerDir -- point -AcademicServerDir at the skill server/ folder"
}

# --- 2. Resolve how paper-search-mcp is launched ------------------------------
# Default: uvx paper-search-mcp (remote, works for anyone). Override with
# -PaperSearchMcpLocalDir to launch a LOCAL checkout via `uv run --directory`.
if ($PaperSearchMcpLocalDir -and (Test-Path $PaperSearchMcpLocalDir)) {
    $psCommand = 'uv'
    $psArgs    = @('run', '--directory', $PaperSearchMcpLocalDir, 'paper-search-mcp')
    $psLabel   = "uv run --directory $PaperSearchMcpLocalDir paper-search-mcp (LOCAL checkout)"
} else {
    $psCommand = 'uvx'
    $psArgs    = @('paper-search-mcp')
    $psLabel   = 'uvx paper-search-mcp'
}
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    Write-Host "WARNING: 'uvx' not on PATH. Install uv/uvx, or pass -PaperSearchMcpLocalDir to use a local checkout."
}

# --- 3. Write mcpServers.json (both servers, native stdio, no Docker) ----------
$config = [ordered]@{
    'paper-search-mcp' = [ordered]@{
        command = $psCommand
        args    = $psArgs
        env     = [ordered]@{
            PAPER_SEARCH_MCP_UNPAYWALL_EMAIL           = $UnpaywallEmail
            PAPER_SEARCH_MCP_LOCAL_DIR                 = $PaperSearchMcpLocalDir
            PAPER_SEARCH_MCP_CORE_API_KEY              = ''
            PAPER_SEARCH_MCP_SEMANTIC_SCHOLAR_API_KEY  = ''
        }
    }
    'academic-mcp' = [ordered]@{
        command = $venvPython
        args    = @($serverPy)
        env     = @{}
    }
} | ConvertTo-Json -Depth 5

if (-not (Test-Path $GrokDir)) { New-Item -ItemType Directory -Path $GrokDir -Force | Out-Null }
if (Test-Path $ConfigPath) {
    Copy-Item $ConfigPath "$ConfigPath.bak" -Force -ErrorAction SilentlyContinue
    Write-Host "Backed up existing config to $ConfigPath.bak"
}
Set-Content -Path $ConfigPath -Value $config -Encoding utf8
Write-Host "Wrote MCP registration to: $ConfigPath"
Write-Host ("academic-mcp: {0} {1}" -f $venvPython, $serverPy)
Write-Host "paper-search-mcp: $psLabel"
Write-Host "Restart the agent runtime so it picks up the servers."
