#!/usr/bin/env python3
"""Three-tool PubMed MCP server for the literature-review skill."""

from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from typing import Any, Literal

import anyio
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations


EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ATTRIBUTION = (
    "Based on records retrieved from PubMed. Cite relevant articles with DOI links."
)
INSTRUCTIONS = (
    "Search PubMed before making biomedical literature claims. Use search_articles, "
    "then get_article_metadata for selected PMIDs; use find_related_articles to "
    "broaden strong seeds. Attribute PubMed-derived information and link every "
    "referenced DOI. Calls are read-only, bounded, rate-limited, and serialized."
)
READ_ONLY = ToolAnnotations(readOnlyHint=True)

mcp = FastMCP("pubmed", instructions=INSTRUCTIONS)


class NCBIClient:
    """Serialized, paced E-utilities client."""

    def __init__(self) -> None:
        self.email = os.environ.get("NCBI_EMAIL", "").strip()
        self.api_key = os.environ.get("NCBI_API_KEY", "").strip()
        self._lock = anyio.Lock()
        self._last_request = 0.0

    def _params(self, params: dict[str, Any]) -> dict[str, Any]:
        result = {**params, "tool": "codex-literature-review"}
        if self.email:
            result["email"] = self.email
        if self.api_key:
            result["api_key"] = self.api_key
        return result

    async def request(
        self, endpoint: str, params: dict[str, Any], *, as_json: bool
    ) -> Any:
        interval = 0.11 if self.api_key else 0.34
        async with self._lock:
            delay = interval - (time.monotonic() - self._last_request)
            if delay > 0:
                await anyio.sleep(delay)
            headers = {"User-Agent": "codex-literature-review/1.0"}
            if self.email:
                headers["User-Agent"] += f" (mailto:{self.email})"
            last_error: Exception | None = None
            # Three attempts plus backoff must remain below Codex's 60-second
            # tool timeout even when the upstream is unreachable.
            async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                for attempt in range(3):
                    try:
                        response = await client.get(
                            f"{EUTILS}/{endpoint}", params=self._params(params)
                        )
                        self._last_request = time.monotonic()
                        if response.status_code in {429, 500, 502, 503, 504}:
                            if attempt < 2:
                                await anyio.sleep(attempt + 1)
                                continue
                        response.raise_for_status()
                        return response.json() if as_json else response.text
                    except (httpx.HTTPError, ValueError) as exc:
                        last_error = exc
                        if attempt < 2:
                            await anyio.sleep(attempt + 1)
                            continue
            raise RuntimeError(f"NCBI E-utilities request failed: {last_error}")


CLIENT = NCBIClient()


def _bounded(value: int, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(1, min(maximum, number))


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = "".join(element.itertext()).strip()
    return value or None


def _article_record(article: ET.Element) -> dict[str, Any]:
    citation = article.find("MedlineCitation")
    pubmed_data = article.find("PubmedData")
    article_node = citation.find("Article") if citation is not None else None

    identifiers: dict[str, str] = {}
    if citation is not None:
        pmid = _text(citation.find("PMID"))
        if pmid:
            identifiers["pmid"] = pmid
    if pubmed_data is not None:
        for item in pubmed_data.findall("ArticleIdList/ArticleId"):
            value = _text(item)
            kind = item.get("IdType")
            if value and kind in {"pubmed", "pmc", "doi"}:
                identifiers["pmid" if kind == "pubmed" else kind] = value

    title = _text(article_node.find("ArticleTitle")) if article_node is not None else None
    abstract_parts: list[str] = []
    if article_node is not None:
        for item in article_node.findall("Abstract/AbstractText"):
            value = _text(item)
            if value:
                label = item.get("Label")
                abstract_parts.append(f"{label}: {value}" if label else value)

    authors: list[str] = []
    if article_node is not None:
        for author in article_node.findall("AuthorList/Author"):
            collective = _text(author.find("CollectiveName"))
            if collective:
                authors.append(collective)
                continue
            family = _text(author.find("LastName"))
            given = _text(author.find("ForeName"))
            name = " ".join(part for part in (given, family) if part)
            if name:
                authors.append(name)

    journal = None
    publication_date: dict[str, str] = {}
    if article_node is not None:
        journal = _text(article_node.find("Journal/Title"))
        date = article_node.find("Journal/JournalIssue/PubDate")
        if date is not None:
            for source, target in (("Year", "year"), ("Month", "month"), ("Day", "day")):
                value = _text(date.find(source))
                if value:
                    publication_date[target] = value

    record: dict[str, Any] = {
        "identifiers": identifiers,
        "title": title,
        "abstract": "\n".join(abstract_parts) or None,
        "authors": authors,
        "journal": journal,
        "publication_date": publication_date,
    }
    if "doi" in identifiers:
        record["doi_url"] = f"https://doi.org/{identifiers['doi']}"
    return record


def parse_pubmed_xml(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    return [_article_record(article) for article in root.findall("PubmedArticle")]


def parse_related(
    payload: dict[str, Any], seeds: list[str], limit: int
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    seed_set = set(seeds)
    for linkset in payload.get("linksets", []):
        links: list[str] = []
        for database in linkset.get("linksetdbs", []):
            if database.get("linkname") == "pubmed_pubmed":
                links.extend(
                    str(value)
                    for value in database.get("links", [])
                    if str(value) not in seed_set
                )
        groups.append(
            {
                "seed_pmids": [str(value) for value in linkset.get("ids", [])],
                "related_pmids": links[:limit],
            }
        )
    return groups


@mcp.tool(annotations=READ_ONLY)
async def search_articles(
    query: str,
    max_results: int = 20,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: Literal["relevance", "pub_date"] = "relevance",
) -> dict[str, Any]:
    """Search biomedical and life-science articles indexed by PubMed.

    Args:
        query: PubMed search expression.
        max_results: Number of PMIDs to return, from 1 to 100.
        date_from: Optional publication start date accepted by NCBI.
        date_to: Optional publication end date accepted by NCBI.
        sort: Relevance or publication-date ordering.
    """
    if not query.strip():
        raise ValueError("query must not be empty")
    limit = _bounded(max_results, default=20, maximum=100)
    params: dict[str, Any] = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": limit,
        "sort": "pub date" if sort == "pub_date" else "relevance",
    }
    if date_from or date_to:
        params["datetype"] = "pdat"
        if date_from:
            params["mindate"] = date_from
        if date_to:
            params["maxdate"] = date_to
    payload = await CLIENT.request("esearch.fcgi", params, as_json=True)
    result = payload.get("esearchresult", {})
    pmids = [str(value) for value in result.get("idlist", [])][:limit]
    return {
        "query": query,
        "total_count": int(result.get("count", 0)),
        "returned_count": len(pmids),
        "pmids": pmids,
        "attribution": ATTRIBUTION,
    }


@mcp.tool(annotations=READ_ONLY)
async def get_article_metadata(pmids: list[str]) -> dict[str, Any]:
    """Fetch titles, abstracts, authors, journals, dates, and DOI links.

    Args:
        pmids: One to fifty PubMed identifiers.
    """
    cleaned = [str(value).strip() for value in pmids if str(value).strip()]
    if not cleaned:
        raise ValueError("provide at least one PMID")
    if len(cleaned) > 50:
        raise ValueError("at most 50 PMIDs are allowed per call")
    if any(not value.isdigit() for value in cleaned):
        raise ValueError("PMIDs must contain digits only")
    xml_text = await CLIENT.request(
        "efetch.fcgi",
        {"db": "pubmed", "id": ",".join(cleaned), "retmode": "xml"},
        as_json=False,
    )
    records = parse_pubmed_xml(xml_text)
    return {
        "requested_pmids": cleaned,
        "returned_count": len(records),
        "articles": records,
        "attribution": ATTRIBUTION,
    }


@mcp.tool(annotations=READ_ONLY)
async def find_related_articles(
    pmids: list[str], max_results: int = 20
) -> dict[str, Any]:
    """Find PubMed articles computationally similar to seed PMIDs.

    Args:
        pmids: One to twenty seed PubMed identifiers.
        max_results: Similar PMIDs to return per seed, from 1 to 100.
    """
    cleaned = [str(value).strip() for value in pmids if str(value).strip()]
    if not cleaned:
        raise ValueError("provide at least one PMID")
    if len(cleaned) > 20:
        raise ValueError("at most 20 seed PMIDs are allowed per call")
    if any(not value.isdigit() for value in cleaned):
        raise ValueError("PMIDs must contain digits only")
    limit = _bounded(max_results, default=20, maximum=100)
    payload = await CLIENT.request(
        "elink.fcgi",
        {
            "dbfrom": "pubmed",
            "db": "pubmed",
            "id": ",".join(cleaned),
            "linkname": "pubmed_pubmed",
            "retmode": "json",
        },
        as_json=True,
    )
    return {
        "groups": parse_related(payload, cleaned, limit),
        "attribution": ATTRIBUTION,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
