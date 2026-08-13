"""
Research-workspace helpers for the academic-research-win skill.

Two jobs, kept deliberately small so a workflow sub-agent can call them
without any install step:

1. **Transient downloads always go to the OS-standard temp folder.**
   `system_tmp_dir()` returns `tempfile.gettempdir()` — on Windows that is
   whatever `TMP`/`TEMP` resolves to (e.g. .../AppData/Local/Temp), i.e. the
   system standard location. No hard-coded app dir, so nothing is silently
   left on a non-standard path.

2. **Collected papers live in a per-topic folder**
   `<research_root>/research/<slugified-topic>/`, defaulting to
   `<skill_root>/research` but overridable via the `ACADEMIC_RESEARCH_ROOT`
   env var (so a sub-agent can point the collection at the actual project
   being researched rather than the skill tree). Each topic folder holds a
   `pdfs/` sub-folder (for downloaded PDFs moved out of the temp dir) and a
   `map.md` index that an AI agent can open to instantly see what research
   artefacts are present and what they say.

The unified paper schema is the one produced by `paper_search_mapping`
(`UNIFIED_FIELDS`). `CollectedPaper.from_unified` converts those dicts into
the richer record used for the `map.md` index, layering on PDF path, source
and citation-chain stats that the search result does not carry.

By default a downloaded PDF is *moved* out of the OS temp folder into the
topic's `pdfs/` collection, and `map.md` never records a temp path. Pass
`keep_in_temp=True` to `place_and_index` only when you explicitly want to leave
a file in the volatile temp folder (e.g. a one-shot consume-then-discard run);
that file is flagged `volatile` in `map.md` so downstream agents know it will
vanish on reboot/cleanup. A `map.md` is never allowed to silently point at a
temp path (fail-closed guard in `write_map_md`).
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from .paper_search_mapping import UNIFIED_FIELDS


def system_tmp_dir() -> Path:
    """The OS-standard temporary folder (on Windows this is the user's
    Local/Temp folder, i.e. whatever TMP/TEMP resolves to — never hard-coded)."""
    return Path(tempfile.gettempdir())


def research_root() -> Path:
    """
    Root under which per-topic research folders are created.

    Override with the `ACADEMIC_RESEARCH_ROOT` env var to collect papers into
    an arbitrary project folder; defaults to `<skill_root>/research`.
    """
    env = os.environ.get("ACADEMIC_RESEARCH_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    # This file lives in <skill_root>/mappings/research_workspace.py
    return Path(__file__).resolve().parents[1] / "research"


def _slug(topic: str) -> str:
    """Stable, filesystem-safe folder name from a free-form topic string."""
    s = re.sub(r"[^0-9a-zA-Z]+", "-", topic.strip().lower()).strip("-")
    return s or "topic"


def topic_dir(topic: str) -> Path:
    """`research/<slug>` directory for a topic (not created here)."""
    return research_root() / "research" / _slug(topic)


def pdfs_dir(topic: str) -> Path:
    """`pdfs/` sub-folder inside a topic directory."""
    return topic_dir(topic) / "pdfs"


def init_topic(topic: str) -> Path:
    """Create (idempotent) `<root>/research/<slug>/` + `pdfs/` + an empty `map.md`."""
    base = _ensure(topic)
    # Touch the map so a fresh folder is always self-describing, even before
    # any paper is collected.
    write_map_md(topic, [])
    return base


def _ensure(topic: str) -> Path:
    """Idempotently create the topic + pdfs dirs and return the topic base."""
    base = topic_dir(topic)
    base.mkdir(parents=True, exist_ok=True)
    pdfs_dir(topic).mkdir(parents=True, exist_ok=True)
    return base


def _filename_for(paper_id: str, pdf_url: str) -> str:
    """Derive a deterministic, filesystem-safe PDF filename from id then URL
    then fallback. All non-alphanumeric runs become `_` (a DOI like
    `10.1000/xyz` or `arxiv:999` is therefore turned into `10_1000_xyz` /
    `arxiv_999` — safe on Windows)."""
    if paper_id and paper_id.strip():
        safe = re.sub(r"[^A-Za-z0-9]+", "_", paper_id.strip()).strip("_")
        if safe:
            return safe + ".pdf"
    if pdf_url:
        name = pdf_url.rstrip("/").rsplit("/", 1)[-1]
        safe = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")
        return (safe + ".pdf") if safe else "paper.pdf"
    return "paper.pdf"


def place_download(tmp_pdf: Path, topic: str, *,
                   paper_id: str = "", pdf_url: str = "") -> Path:
    """
    Move a transient PDF downloaded to the system temp folder into the
    topic's `pdfs/` collection. Returns its path **relative to the topic dir**.

    The caller is responsible for having written `tmp_pdf` into
    `system_tmp_dir()`; this just relocates it into the permanent collection
    so the temp folder stays the single transient scratch space.
    """
    base = init_topic(topic)
    name = _filename_for(paper_id, pdf_url)
    dest = pdfs_dir(topic) / name
    shutil.move(str(tmp_pdf), str(dest))
    # Relative to the topic dir so map.md stays portable across machines.
    rel = dest.relative_to(base).as_posix()
    return dest  # absolute; callers that need a relative path can rebase


def place_download_rel(tmp_pdf: Path, topic: str, *,
                       paper_id: str = "", pdf_url: str = "") -> str:
    """Like `place_download` but returns the path relative to the topic dir."""
    base = init_topic(topic)
    dest = place_download(tmp_pdf, topic, paper_id=paper_id, pdf_url=pdf_url)
    return dest.relative_to(base).as_posix()


@dataclass
class CollectedPaper:
    """A unified paper + the collection metadata the search result lacks."""
    doi_or_arxiv_id: str = ""
    title: str = ""
    first_author: str = ""
    year: int = 0
    citation_count: int = 0
    is_open_access: bool = False
    abstract: str = ""
    # extra, workflow-side fields (not in UNIFIED_FIELDS)
    source: str = ""
    pdf_path_rel: str = ""   # relative-to-topic-dir path, "" if not fetched
    pdf_path_abs: str = ""   # absolute Temp path when volatile (keep_in_temp); else ""
    volatile: bool = False   # True only when intentionally kept in the OS temp dir
    chain_cites: int = 0     # hop-1 forward (cites) count from citation_chain
    chain_refs: int = 0      # hop-1 backward (refs) count
    notes: str = ""

    @classmethod
    def from_unified(cls, unified: dict, **extras: Any) -> "CollectedPaper":
        """Build from a dict returned by `normalize_paper`/`normalize_search_papers_results`."""
        if not isinstance(unified, dict):
            raise TypeError(f"from_unified expects a dict, got {type(unified).__name__}")
        missing = [f for f in UNIFIED_FIELDS if f not in unified]
        if missing:
            raise ValueError(f"unified dict missing fields: {missing}")
        data: dict = {f: unified[f] for f in UNIFIED_FIELDS}
        data.update(extras)
        return cls(**data)

    def as_dict(self) -> dict:
        out: dict = {f: getattr(self, f) for f in UNIFIED_FIELDS}
        out.update(
            source=self.source,
            pdf_path_rel=self.pdf_path_rel,
            pdf_path_abs=self.pdf_path_abs,
            volatile=self.volatile,
            chain_cites=self.chain_cites,
            chain_refs=self.chain_refs,
            notes=self.notes,
        )
        return out


def write_map_md(
    topic: str,
    papers: Iterable[CollectedPaper] | Iterable[dict],
    *,
    chain_stats: Optional[dict] = None,
    notes: str = "",
    header: Optional[dict] = None,
) -> Path:
    """
    Write/overwrite `map.md` in the topic folder.

    `papers` may be `CollectedPaper` instances or raw unified dicts (they are
    coerced via `from_unified` so the index and the normalizer never drift).
    `chain_stats` (if given) documents the citation-chain run that produced
    the collection, e.g. `{"direction": "cites", "depth": 1, "hop1": 18}`.

    The file is valid, stable markdown so a downstream AI agent can `read` it
    and immediately know: what the topic is, where the PDFs live, and for
    every paper its id/title/authors/year/oa-status plus the chain result.
    """
    base = _ensure(topic)
    collected: list[CollectedPaper] = []
    for p in papers:
        if isinstance(p, CollectedPaper):
            collected.append(p)
        elif isinstance(p, dict):
            collected.append(CollectedPaper.from_unified(p))
        else:
            raise TypeError(f"unsupported paper type: {type(p).__name__}")

    # Fail-closed: a durable map.md must never silently point at the volatile OS
    # temp folder. A temp path is only ever recorded when the caller explicitly
    # opted in (volatile=True); anything else is a bug, not something to hide.
    tmp = str(system_tmp_dir())
    for p in collected:
        if p.pdf_path_abs and not p.volatile:
            raise ValueError(
                f"refusing to index a temp/absolute path {p.pdf_path_abs!r} without "
                f"volatile=True (pass keep_in_temp=True to place_and_index to opt in)")

    hdr = {"topic": topic, "slug": _slug(topic)}
    if header:
        hdr.update(header)

    lines: list[str] = []
    lines.append(f"# Research map — {hdr['topic']}")
    lines.append("")
    lines.append("| field | value |")
    lines.append("|---|---|")
    lines.append(f"| topic | {hdr['topic']} |")
    lines.append(f"| slug | `{hdr['slug']}` |")
    base_rel = base.relative_to(base.parent)  # -> research/<slug>
    lines.append("| collection | `research/{slug}/` (this folder) |")
    lines.append("| pdfs | `pdfs/` — downloaded PDFs, moved here from the system temp dir |")
    n_vol = sum(1 for p in collected if p.volatile)
    if n_vol:
        lines.append(f"| ⚠ volatile | {n_vol} PDF(s) intentionally kept in the OS temp folder "
                     f"(volatile — lost on reboot/cleanup); re-collect before relying on them |")
    if chain_stats:
        lines.append(f"| citation chain | direction={chain_stats.get('direction','?')}, "
                     f"depth={chain_stats.get('depth','?')}, hop1={chain_stats.get('hop1','?')}")
    lines.append("")
    if notes:
        lines.append("## Notes")
        lines.append(notes.rstrip())
        lines.append("")
    lines.append("## Collected papers")
    if not collected:
        lines.append("_No papers collected yet. Run `paper-search-mcp__search_papers` and "
                     "`place_download` from `research_workspace` to populate this index._")
        lines.append("")
    else:
        lines.append("| # | id / DOI | title | first author | year | cites (search) | OA PDF | chain cites | pdf |")
        lines.append("|---|----------|-------|--------------|------|-----------------|--------|--------------|-----|")
        for i, p in enumerate(collected, 1):
            title_short = (p.title[:60] + "…") if len(p.title) > 60 else (p.title or "—")
            if p.pdf_path_rel:
                pdf_cell = f"`pdfs/{p.pdf_path_rel.split('/')[-1]}`"
            elif p.volatile and p.pdf_path_abs:
                pdf_cell = f"`{p.pdf_path_abs}` ⚠ volatile (OS temp)"
            else:
                pdf_cell = "—"
            lines.append(
                f"| {i} | `{p.doi_or_arxiv_id or '—'}` | {title_short} | "
                f"{p.first_author or '—'} | {p.year or '—'} | {p.citation_count or 0} | "
                f"{'yes' if p.is_open_access else 'no'} | {p.chain_cites or 0} | {pdf_cell} |"
            )
        lines.append("")
        # Full abstracts as collapsible sections so an agent has the text in-band.
        lines.append("### Abstracts")
        for i, p in enumerate(collected, 1):
            lines.append(f"#### {i}. {p.title or p.doi_or_arxiv_id or 'paper'}")
            lines.append(f"_id: `{p.doi_or_arxiv_id or '—'}` · source: {p.source or '—'}_")
            lines.append("")
            lines.append(p.abstract or "_no abstract returned_")
            lines.append("")
    out = base / "map.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def place_and_index(
    tmp_pdf: Path,
    topic: str,
    paper_unified: dict,
    *,
    chain_cites: int = 0,
    chain_refs: int = 0,
    notes: str = "",
    chain_stats: Optional[dict] = None,
    keep_in_temp: bool = False,
) -> CollectedPaper:
    """
    Move a temp PDF into the topic `pdfs/` folder *and* refresh `map.md`,
    returning the `CollectedPaper` record that was indexed.

    Unless ``keep_in_temp`` is set, the staging file is **moved** (not copied)
    out of the OS temp folder into the permanent `pdfs/` collection and the
    temp path is never recorded in `map.md` (fail-closed).

    ``keep_in_temp=True`` is an explicit opt-in: the file is left in place in
    the volatile OS temp folder and `map.md` flags it `volatile` so downstream
    agents know it will vanish on reboot/cleanup. Use it only for one-shot
    consume-then-discard runs -- the default (move to `pdfs/`) is almost always
    what you want.
    """
    tmp_pdf = Path(tmp_pdf)
    base = init_topic(topic)
    paper_id = paper_unified.get("doi_or_arxiv_id", "")
    # pdf_url lives under its original key on the raw search-paper dict, but
    # normalize_paper drops it; accept either spelling.
    pdf_url = paper_unified.get("pdf_url", "")

    if keep_in_temp:
        # Intentional: do NOT migrate off the volatile OS temp folder. The
        # staging file must actually be present (you can't "keep" what isn't
        # there) and must be sitting in the system temp dir.
        if not tmp_pdf.exists():
            raise FileNotFoundError(
                f"keep_in_temp=True requires a staging PDF in {system_tmp_dir()}; "
                f"missing: {tmp_pdf}")
        if not str(tmp_pdf).startswith(str(system_tmp_dir())):
            raise ValueError(
                f"keep_in_temp=True refuses a non-temp source (must live under "
                f"{system_tmp_dir()}); got {tmp_pdf}")
        pdf_path_rel = ""
        pdf_path_abs = str(tmp_pdf)
        print("  [keep_in_temp] PDF left in volatile OS temp folder "
              "(will be lost on reboot/cleanup)", flush=True)
    else:
        rel = place_download_rel(tmp_pdf, topic, paper_id=paper_id, pdf_url=pdf_url)
        pdf_path_rel = rel
        pdf_path_abs = ""
        # Fail-closed: the staging file must be gone (moved into pdfs/).
        assert not tmp_pdf.exists(), (
            f"temp PDF still present at {tmp_pdf} after move -- collection may be incomplete")

    rec = CollectedPaper.from_unified(
        paper_unified,
        pdf_path_rel=pdf_path_rel,
        pdf_path_abs=pdf_path_abs,
        chain_cites=int(chain_cites),
        chain_refs=int(chain_refs),
        notes=notes,
        volatile=keep_in_temp,
    )
    # Re-write map.md so it records the citation-chain run that produced this
    # collection (direction/depth/hop1 live in the header table for the next
    # AI agent that opens the folder).
    write_map_md(topic, [rec], chain_stats=chain_stats,
                 notes=(notes or "auto-indexed on placement"))
    return rec
