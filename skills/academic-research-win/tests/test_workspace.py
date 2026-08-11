"""
Hermetic tests for the research-workspace helpers (`mappings/research_workspace`).

These never touch the real `research/` tree or the network: every test sets
`ACADEMIC_RESEARCH_ROOT` to a pytest `tmp_path` (or builds records from the
normalized shape produced by the mapping tests). They pin:

  * transient downloads land in the OS-standard temp folder,
  * per-topic folders are created at `<root>/research/<slug>/`,
  * a temp PDF is *moved* (not copied) out of the temp folder into
    `<topic>/pdfs/`,
  * `map.md` is written for raw dicts and `CollectedPaper` records alike and
    stays in sync with `UNIFIED_FIELDS`,
  * `CollectedPaper.from_unified` rejects partial unified dicts.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from mappings import research_workspace as rw
from mappings.paper_search_mapping import UNIFIED_FIELDS

SAMPLE = {
    "doi_or_arxiv_id": "2201.00978v1",
    "title": "PyramidTNT: Improved Transformer-in-Transformer Baselines",
    "first_author": "Kai Han",
    "year": 2022,
    "citation_count": 18,
    "is_open_access": True,
    "abstract": "Transformer networks have achieved great progress …",
    # extra keys the raw search result carries (kept; the workspace ignores them)
    "source": "arxiv",
    "pdf_url": "https://arxiv.org/pdf/2201.00978",
}


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    """Point research_root() at a throwaway dir for the duration of one test."""
    root = tmp_path / "proj"
    monkeypatch.setenv("ACADEMIC_RESEARCH_ROOT", str(root))
    yield root


# 1. system_tmp_dir -----------------------------------------------------------------
def test_system_tmp_dir_is_os_standard():
    """The transient download dir must be the OS temp (never hard-coded)."""
    expected = Path(tempfile.gettempdir())
    assert rw.system_tmp_dir() == expected


# 2. research_root + slug -----------------------------------------------------------
def test_research_root_uses_env_override(isolated_root):
    assert rw.research_root() == isolated_root.resolve()
    # env override takes precedence over the skill-default
    assert rw.topic_dir("My Topic") == isolated_root / "research" / "my-topic"


def test_research_root_default_is_under_skill(isolated_root):
    isolated_root  # touch; we test the *non-override* path explicitly
    import mappings.research_workspace as _rw
    # Without the env var the root is <skill_root>/research; verify parentage.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.delenv("ACADEMIC_RESEARCH_ROOT", raising=False)
    root = _rw.research_root()
    assert root.name == "research"
    assert root.parent.name != "research"  # i.e. it's <skill>/research, not nested
    monkeypatch.undo()


@pytest.mark.parametrize(
    "topic, want",
    [
        ("Attention Is All You Need", "attention-is-all-you-need"),
        ("  SpaCy NLP  ", "spacy-nlp"),
        ("A.B:C/D", "a-b-c-d"),
        ("transformers, 2024", "transformers-2024"),
        ("", "topic"),  # empty/blank topic -> safe fallback
    ],
)
def test_slug_is_filesystem_safe(topic, want):
    assert rw._slug(topic) == want


# 3. init_topic layout --------------------------------------------------------------
def test_init_topic_creates_layout_and_map(isolated_root):
    base = rw.init_topic("Vision Transformers")
    assert base == isolated_root / "research" / "vision-transformers"
    assert base.is_dir()
    assert (base / "pdfs").is_dir()
    map_md = base / "map.md"
    assert map_md.is_file()
    text = map_md.read_text(encoding="utf-8")
    assert "Research map — Vision Transformers" in text
    assert "`pdfs/` — downloaded PDFs" in text


# 4. place_download moves a temp PDF ------------------------------------------------
def test_place_download_moves_tmp_into_pdfs(isolated_root, tmp_path):
    base = rw.init_topic("Cited Papers")
    tmp = rw.system_tmp_dir()
    src = tmp / "dl_buffer_12345.pdf"
    src.write_bytes(b"%PDF-1.4 fake pdf payload")
    moved = rw.place_download(src, "Cited Papers", paper_id="arxiv:999",
                              pdf_url="https://x.org/pdf/999")
    # source must be gone (a move, not a copy)
    assert not src.exists()
    # destination is inside the topic's pdfs/
    assert moved == isolated_root / "research" / "cited-papers" / "pdfs" / "arxiv_999.pdf"
    assert moved.is_file()
    assert moved.read_bytes() == b"%PDF-1.4 fake pdf payload"


def test_place_download_rel_returns_path_relative_to_topic(isolated_root, tmp_path):
    tmp = rw.system_tmp_dir()
    src = tmp / "dl_buffer_rel.pdf"
    src.write_bytes(b"data")
    rel = rw.place_download_rel(src, "Topic X", paper_id="10.1000/xyz")
    # no 'pdfs' in the *absolute* path is fine; the rel form must be portable
    assert rel == "pdfs/10_1000_xyz.pdf"
    assert not src.exists()


# 5. CollectedPaper.from_unified contract ------------------------------------------
def test_from_unified_accepts_full_record():
    rec = rw.CollectedPaper.from_unified(SAMPLE, chain_cites=18)
    assert rec.doi_or_arxiv_id == "2201.00978v1"
    assert rec.title == "PyramidTNT: Improved Transformer-in-Transformer Baselines"
    assert rec.first_author == "Kai Han"
    assert rec.year == 2022
    assert rec.citation_count == 18
    assert rec.is_open_access is True
    assert rec.chain_cites == 18
    # unified fields surface through as_dict()
    d = rec.as_dict()
    for f in UNIFIED_FIELDS:
        assert f in d


def test_from_unified_rejects_missing_fields():
    bad = {k: v for k, v in SAMPLE.items() if k != "abstract"}
    with pytest.raises(ValueError, match="missing fields"):
        rw.CollectedPaper.from_unified(bad)


# 6. write_map_md coerces raw dicts + indexes chain stats --------------------------
def test_write_map_md_indexes_raw_dict(isolated_root):
    base = rw.init_topic("Chain Test")
    out = rw.write_map_md(
        "Chain Test",
        [SAMPLE],
        chain_stats={"direction": "cites", "depth": 1, "hop1": 18},
        notes="seeded from search_papers",
    )
    assert out == base / "map.md"
    text = out.read_text(encoding="utf-8")
    # header
    assert "# Research map — Chain Test" in text
    assert "slug | `chain-test`" in text
    assert "citation chain | direction=cites, depth=1, hop1=18" in text
    assert "seeded from search_papers" in text
    # table row with the unified id + title (truncated to 60)
    assert "`2201.00978v1`" in text
    assert "PyramidTNT: Improved Transformer-in-Transformer Baselines" in text
    # abstract rendered in-band for the agent
    assert "## Abstracts" in text
    assert "Transformer networks have achieved great progress" in text


def test_write_map_md_empty_collection(isolated_root):
    base = rw.init_topic("Empty")
    out = rw.write_map_md("Empty", [])
    assert (out).is_file()
    assert "No papers collected yet" in out.read_text(encoding="utf-8")


# 7. place_and_index end-to-end -----------------------------------------------------
def test_place_and_index_end_to_end(isolated_root):
    tmp = rw.system_tmp_dir()
    src = tmp / "dl_e2e.pdf"
    src.write_bytes(b"e2e pdf")
    rec = rw.place_and_index(
        src, "E2E Topic", SAMPLE, chain_cites=18, chain_refs=7,
        notes="placed from system temp",
        chain_stats={"direction": "cites", "depth": 1, "hop1": 18},
    )
    base = isolated_root / "research" / "e2e-topic"
    assert not src.exists()  # moved out of the OS temp folder
    assert (base / "pdfs" / "2201_00978v1.pdf").exists()
    map_md = base / "map.md"
    text = map_md.read_text(encoding="utf-8")
    # indexed paper + chain stats present
    assert "`2201.00978v1`" in text
    assert "citation chain | direction=cites, depth=1, hop1=18" in text  # chain run recorded in header
    assert "| 18 |" in text                                            # 18 search-cites + 18 chain-cites in the data row
    # the returned record's pdf_path_rel is portable (relative to topic dir)
    assert rec.pdf_path_rel == "pdfs/2201_00978v1.pdf"
    assert rec.chain_cites == 18 and rec.chain_refs == 7
    # default path is NOT volatile: nothing temp survives in map.md
    assert rec.volatile is False
    assert rec.pdf_path_abs == ""
    assert "volatile" not in text.lower()


# 8. keep_in_temp opt-in (explicitly stay in the volatile OS temp folder) -----------
def test_place_and_index_keep_in_temp_leaves_file_and_flags_volatile(isolated_root):
    tmp = rw.system_tmp_dir()
    src = tmp / "dl_keep_volatile.pdf"
    src.write_bytes(b"keep-me-in-temp")
    try:
        rec = rw.place_and_index(
            src, "Keep Topic", SAMPLE, chain_cites=18, keep_in_temp=True,
            notes="intentionally left in OS temp",
            chain_stats={"direction": "cites", "depth": 1, "hop1": 18},
        )
        # file STAYS in the OS temp folder (not migrated into pdfs/)
        assert src.exists(), "keep_in_temp must leave the file in the temp folder"
        pdfs = rw.pdfs_dir("Keep Topic")
        assert not (pdfs / "2201_00978v1.pdf").exists()
        # record marks it volatile with the absolute temp path
        assert rec.volatile is True
        assert rec.pdf_path_abs == str(src)
        assert rec.pdf_path_rel == ""
        # map.md flags it as volatile instead of silently indexing a temp path
        text = (rw.topic_dir("Keep Topic") / "map.md").read_text(encoding="utf-8")
        assert "volatile" in text.lower()
        assert str(src) in text
    finally:
        if src.exists():
            src.unlink(missing_ok=True)


def test_place_and_index_default_moves_and_clears_volatile_flag(isolated_root):
    tmp = rw.system_tmp_dir()
    src = tmp / "dl_default_volatile.pdf"
    src.write_bytes(b"move-me")
    rec = rw.place_and_index(src, "Default Topic", SAMPLE, chain_cites=18)
    # default migrates the file -> it is gone from temp, present in pdfs/
    assert not src.exists()
    assert (rw.pdfs_dir("Default Topic") / "2201_00978v1.pdf").exists()
    assert rec.volatile is False
    assert rec.pdf_path_rel == "pdfs/2201_00978v1.pdf"
    text = (rw.topic_dir("Default Topic") / "map.md").read_text(encoding="utf-8")
    assert "volatile" not in text.lower()


def test_place_and_index_keep_in_temp_refuses_missing_source(isolated_root):
    # keep_in_temp=True must refuse when the staging file is not actually there
    # (you can't "keep" what isn't present -> fail closed, not silent).
    missing = rw.system_tmp_dir() / "dl_definitely_missing.pdf"
    assert not missing.exists()
    with pytest.raises((FileNotFoundError, ValueError), match="keep_in_temp"):
        rw.place_and_index(missing, "Missing Topic", SAMPLE, keep_in_temp=True)
