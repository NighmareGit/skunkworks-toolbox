"""
Tests for the paper-search-mcp → academic-research workflow output mapping.

This is the executable contract for the field remapping that the rewritten
workflow's Stage-2 sub-agents must follow. paper-search-mcp's Paper.to_dict()
returns a different schema than the original academic-mcp
`academic_search` result; these tests pin the translation so the downstream
Stages 3/4/5/6 prompts stay stable.

Field map (paper-search-mcp -> workflow unified schema):
    doi_or_arxiv_id   <- doi (fallback paper_id, then url)
    title             <- title
    first_author      <- first token of `authors` ("; "-joined)
    year              <- int(published_date[:4])  (0 when blank)
    citation_count    <- citations (int, default 0)
    is_open_access    <- bool(pdf_url)   (heuristic; paper-search-mcp has no explicit OA flag)
    abstract          <- abstract
"""
import pytest

from mappings.paper_search_mapping import (
    normalize_paper,
    normalize_search_papers_results,
    best_work_id_for_openalex,
)

# A representative paper-search-mcp Paper.to_dict() payload.
SAMPLE = {
    "paper_id": "2312.12456",
    "title": "Attention Is All You Need",
    "authors": "Vaswani, Ashish; Shazeer, Noam; Parmar, Niki",
    "abstract": "The dominant sequence transduction models ...",
    "doi": "10.48550/arXiv.1706.03762",
    "published_date": "2017-06-12T00:00:00",
    "pdf_url": "https://arxiv.org/pdf/1706.03762",
    "url": "https://arxiv.org/abs/1706.03762",
    "source": "arxiv",
    "citations": 104000,
}


# --- single-paper mapping -------------------------------------------------

def test_normalize_basics_with_doi():
    out = normalize_paper(SAMPLE)
    assert out["doi_or_arxiv_id"] == "10.48550/arXiv.1706.03762"
    assert out["title"] == "Attention Is All You Need"
    assert out["first_author"] == "Vaswani, Ashish"
    assert out["year"] == 2017
    assert out["citation_count"] == 104000
    assert out["is_open_access"] is True
    assert out["abstract"] == "The dominant sequence transduction models ..."


def test_first_author_is_first_of_semicolon_string():
    p = dict(SAMPLE, authors="Doe, Jane; Roe, John; Smith, Sam")
    assert normalize_paper(p)["first_author"] == "Doe, Jane"


def test_first_author_when_authors_empty():
    p = dict(SAMPLE, authors="")
    assert normalize_paper(p)["first_author"] == ""


def test_arxiv_id_fallback_when_doi_blank():
    p = dict(SAMPLE, doi="")
    assert normalize_paper(p)["doi_or_arxiv_id"] == "2312.12456"


# --- Stage-3 citation-chain seed selection (DOI preference, no URL) ------------
# Mirrors the `.rhai` Stage-3 rule ("prefer doi; if blank, use paper_id;
# else url") but tightened for OpenAlex: a bare URL is NOT a safe seed because
# OpenAlex cannot map a landing-page URL to a Work id without fragile title
# matching. `best_work_id_for_openalex` returns DOI > arXiv id > "".
#

def test_best_work_id_prefers_doi():
    assert best_work_id_for_openalex(SAMPLE) == SAMPLE["doi"]


def test_best_work_id_falls_back_to_arxiv_id():
    p = dict(SAMPLE, doi="")
    assert best_work_id_for_openalex(p) == p["paper_id"]


def test_best_work_id_does_not_return_url():
    # A bare URL is not a safe citation-chain seed -> empty string, not the url.
    p = {"paper_id": "", "doi": "", "url": "https://arxiv.org/abs/1706.03762"}
    assert best_work_id_for_openalex(p) == ""


def test_best_work_id_empty_when_no_ids():
    assert best_work_id_for_openalex({"title": "x"}) == ""


def test_doi_wins_over_paper_id():
    assert normalize_paper(SAMPLE)["doi_or_arxiv_id"] == SAMPLE["doi"]


def test_year_from_published_date():
    p = dict(SAMPLE, published_date="2023-01-05T00:00:00")
    assert normalize_paper(p)["year"] == 2023


def test_year_zero_when_date_blank():
    assert normalize_paper(dict(SAMPLE, published_date=""))["year"] == 0


def test_is_open_access_false_when_no_pdf_url():
    assert normalize_paper(dict(SAMPLE, pdf_url=""))["is_open_access"] is False


def test_citations_default_zero():
    p = dict(SAMPLE)
    del p["citations"]
    assert normalize_paper(p)["citation_count"] == 0


def test_citations_coerced_to_int():
    p = dict(SAMPLE, citations="42")
    assert normalize_paper(p)["citation_count"] == 42
    assert isinstance(normalize_paper(p)["citation_count"], int)


def test_abstract_passed_through():
    p = dict(SAMPLE, abstract="some abstract text")
    assert normalize_paper(p)["abstract"] == "some abstract text"


# --- list mapping ---------------------------------------------------------

def test_normalize_list_preserves_order_and_count():
    papers = [
        dict(SAMPLE, title="first"),
        dict(SAMPLE, title="second", doi="10.48550/arXiv.9999.00001"),
    ]
    out = normalize_search_papers_results(papers)
    assert len(out) == 2
    assert out[0]["title"] == "first"
    assert out[1]["title"] == "second"
    assert out[1]["doi_or_arxiv_id"] == "10.48550/arXiv.9999.00001"


def test_normalize_empty_list():
    assert normalize_search_papers_results([]) == []
