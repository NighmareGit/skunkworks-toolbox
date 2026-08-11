"""
Consistency tests for the rewritten `academic-research.rhai` workflow.

These guard the hybrid contract: Stage 2 search + Stage 4 evidence use
`paper-search-mcp` tools; Stage 3 citation chaining keeps the vendored
`academic-mcp` tool (the unique capability paper-search-mcp lacks); and the
deprecated academic-mcp search/get_paper/tldr tools no longer appear in the
search/evidence stages.

The workflow text is the source of truth (the sub-agent prompts embed the
exact `use_tool(...)` names), so we assert on the raw file content.
"""
import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "academic-research.rhai"


def read_workflow():
    assert WORKFLOW.exists(), f"workflow not found: {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_file_exists():
    read_workflow()  # asserts existence above


def test_stage2_uses_paper_search_mcp():
    text = read_workflow()
    assert "paper-search-mcp__search_papers" in text


def test_stage2_does_not_use_old_academic_search():
    text = read_workflow()
    assert "academic-mcp__academic_search" not in text


def test_stage3_keeps_academic_mcp_citation_chain():
    text = read_workflow()
    # The one capability paper-search-mcp has no equivalent for.
    assert "academic-mcp__citation_chain" in text


def test_stage4_does_not_use_academic_get_paper():
    text = read_workflow()
    assert "academic_get_paper" not in text
    assert "academic-mcp__academic_get_paper" not in text


def test_no_academic_tldr_reference():
    text = read_workflow()
    assert "tldr" not in text.lower()


def test_workflow_mentions_paper_search_mcp():
    text = read_workflow()
    assert "paper-search-mcp" in text


def test_no_docker_requirement_mentioned():
    text = read_workflow()
    # Native Windows; never require a container.
    assert "docker" not in text.lower()
