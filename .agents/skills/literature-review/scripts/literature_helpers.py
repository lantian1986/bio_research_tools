#!/usr/bin/env python3
"""Deterministic Crossref/OpenAlex helpers for the literature-review skill."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


VERSION = 1
DOI_PATTERN = r"10\.\d{4,9}/[^\s\"'`\]\}—–&|]+"
CONTACT_ENV = "LITERATURE_REVIEW_EMAIL"


def _user_agent() -> str:
    contact = os.environ.get(CONTACT_ENV, "").strip()
    suffix = f" (mailto:{contact})" if contact else ""
    return f"codex-literature-review/1.0{suffix}".encode(
        "ascii", "ignore"
    ).decode("ascii")


def _get_json(url: str, timeout: float = 20) -> dict[str, Any] | None:
    request = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(1.0 * (attempt + 1))
                continue
            return None
        except (OSError, ValueError, json.JSONDecodeError):
            return None
    return None


def _head_status(url: str, timeout: float = 12) -> int | None:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    request = urllib.request.Request(
        url, headers={"User-Agent": _user_agent()}, method="HEAD"
    )
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError:
        return None


def _quote_doi(doi: str) -> str:
    return "/".join(
        urllib.parse.quote(urllib.parse.unquote(segment), safe="")
        for segment in doi.split("/")
    )


def _year(record: dict[str, Any]) -> int | None:
    parts = (record.get("published") or {}).get("date-parts") or [[None]]
    return (parts[0] or [None])[0]


def verify_dois(payload: dict[str, Any]) -> dict[str, Any]:
    dois = payload.get("dois")
    if not isinstance(dois, list) or not all(isinstance(item, str) for item in dois):
        raise ValueError("'dois' must be a list of strings")
    results: dict[str, dict[str, Any]] = {}
    for raw in dois:
        doi = raw.strip()
        if not doi:
            continue
        segments = urllib.parse.unquote(doi).split("/")
        if len(segments) < 2 or any(part in {"", ".", ".."} for part in segments[1:]):
            results[doi] = {"ok": False, "error": "invalid DOI path"}
            continue
        encoded = _quote_doi(doi)
        response = _get_json(f"https://api.crossref.org/works/{encoded}")
        message = (response or {}).get("message")
        if isinstance(message, dict):
            title = (message.get("title") or [""])[0]
            updates = [entry.get("type", "") for entry in message.get("update-to", [])]
            retracted = (
                any("retract" in str(value).lower() for value in updates)
                or str(message.get("subtype", "")).lower() == "retraction"
                or str(title).upper().startswith("RETRACTED")
            )
            results[doi] = {
                "ok": True,
                "title": title,
                "year": _year(message),
                "journal": (message.get("container-title") or [""])[0],
                "retracted": retracted,
                "registry": "crossref",
            }
            continue
        status = _head_status(f"https://doi.org/{encoded}")
        if status is not None and 200 <= status < 400:
            results[doi] = {
                "ok": True,
                "registry": "non-crossref",
                "retracted": None,
            }
        elif status == 404:
            results[doi] = {"ok": False}
        else:
            results[doi] = {
                "ok": None,
                "error": "unverified (network or registry error)",
                "retracted": None,
            }
    return results


def crossref_lookup(payload: dict[str, Any]) -> dict[str, Any] | None:
    reference = payload.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("'reference' must be a non-empty string")
    query = urllib.parse.quote(reference)
    response = _get_json(
        f"https://api.crossref.org/works?query.bibliographic={query}&rows=1"
    )
    items = (response or {}).get("message", {}).get("items", [])
    if not items:
        return None
    record = items[0]
    return {
        "doi": record.get("DOI"),
        "title": (record.get("title") or [""])[0],
        "year": _year(record),
        "score": record.get("score"),
    }


def _openalex_row(record: dict[str, Any]) -> dict[str, Any]:
    location = record.get("primary_location") or {}
    return {
        "doi": str(record.get("doi") or "").removeprefix("https://doi.org/"),
        "title": record.get("title"),
        "year": record.get("publication_year"),
        "cited_by": record.get("cited_by_count"),
        "venue": (location.get("source") or {}).get("display_name"),
        "oa_url": (record.get("open_access") or {}).get("oa_url"),
    }


def _mailto() -> str:
    contact = os.environ.get(CONTACT_ENV, "").strip()
    return f"&mailto={urllib.parse.quote(contact)}" if contact else ""


def search_openalex(payload: dict[str, Any]) -> list[dict[str, Any]]:
    query = payload.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("'query' must be a non-empty string")
    limit = max(1, min(25, int(payload.get("limit", 10))))
    filters = payload.get("filters", "")
    if not isinstance(filters, str):
        raise ValueError("'filters' must be a string")
    filter_arg = f"&filter={urllib.parse.quote(filters, safe=':,|')}" if filters else ""
    response = _get_json(
        "https://api.openalex.org/works"
        f"?search={urllib.parse.quote(query)}&per-page={limit}"
        f"&sort=cited_by_count:desc{filter_arg}{_mailto()}"
    )
    return [_openalex_row(row) for row in (response or {}).get("results", [])[:limit]]


def expand_citations(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    doi = payload.get("doi")
    if not isinstance(doi, str) or not doi.strip():
        raise ValueError("'doi' must be a non-empty string")
    backward = max(1, min(100, int(payload.get("backward_limit", 50))))
    forward = max(1, min(100, int(payload.get("forward_limit", 15))))
    work = _get_json(
        f"https://api.openalex.org/works/doi:{_quote_doi(doi.strip())}"
        f"?select=id{_mailto()}"
    )
    work_id = str((work or {}).get("id") or "").rsplit("/", 1)[-1]
    if not work_id:
        return {"references": [], "cited_by": []}

    def fetch(filter_expression: str, limit: int) -> list[dict[str, Any]]:
        response = _get_json(
            "https://api.openalex.org/works"
            f"?filter={filter_expression}"
            "&select=doi,title,publication_year,cited_by_count"
            f"&sort=cited_by_count:desc&per-page={limit}{_mailto()}"
        )
        return [_openalex_row(row) for row in (response or {}).get("results", [])]

    return {
        "references": fetch(f"cited_by:{work_id}", backward),
        "cited_by": fetch(f"cites:{work_id}", forward),
    }


def extract_dois(payload: dict[str, Any]) -> list[str]:
    text = payload.get("text")
    if not isinstance(text, str):
        raise ValueError("'text' must be a string")
    decoded = (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
        .replace("&nbsp;", " ")
        .replace("&#x2F;", "/")
        .replace("&#47;", "/")
    )
    results: set[str] = set()
    for match in re.findall(DOI_PATTERN, decoded):
        doi = match.split("</")[0]
        if doi.count("<") != doi.count(">"):
            doi = doi.split("<")[0]
        doi = re.sub(r"(?:\*\*|__|[_\]\*>`,;:])+$", "", doi)
        doi = doi[:-1] if doi.endswith(".") else doi
        while doi.endswith(")") and doi.count("(") < doi.count(")"):
            doi = doi[:-1]
        if len(doi) > 8:
            results.add(doi)
    return sorted(results)


def style_pass(payload: dict[str, Any]) -> dict[str, Any]:
    draft = payload.get("draft")
    if not isinstance(draft, str):
        raise ValueError("'draft' must be a string")
    issues: list[dict[str, str]] = []
    words = len(draft.split()) or 1
    em_dashes = draft.count("—")
    if em_dashes > 6 and 1000 * em_dashes / words > 8:
        issues.append({"code": "EMDASH", "note": "replace most em-dashes"})
    if re.search(
        r"\b(the\s+|an?\s+)?honest(ly)?\s+"
        r"(answer|summary|read|perspective|assessment|take|view)\b",
        draft,
        re.I,
    ):
        issues.append({"code": "HONEST", "note": "remove honesty framing"})
    if re.search(
        r"(DOIs?\s+(were\s+)?verif|verified against (CrossRef|PubMed)|"
        r"no retraction|current as of)",
        draft,
        re.I,
    ):
        issues.append({"code": "PROCNOTE", "note": "remove process narration"})
    if re.search(r"\]\(https://doi\.org/[^)\s]*\([^)\s]*\)", draft):
        issues.append({"code": "PARENDOI", "note": "URL-encode DOI parentheses"})
    return {"ok": not issues, "issues": issues}


COMMANDS = {
    "verify-dois": verify_dois,
    "crossref-lookup": crossref_lookup,
    "search-openalex": search_openalex,
    "expand-citations": expand_citations,
    "extract-dois": extract_dois,
    "style-pass": style_pass,
}


def _read_payload(path: str) -> dict[str, Any]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    if value.get("version") != VERSION:
        raise ValueError(f"'version' must be {VERSION}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("input", help="JSON input path, or - for stdin")
    args = parser.parse_args()
    try:
        result = COMMANDS[args.command](_read_payload(args.input))
        envelope = {"version": VERSION, "ok": True, "result": result}
        print(json.dumps(envelope, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"literature-helper: {exc}", file=sys.stderr)
        print(
            json.dumps(
                {"version": VERSION, "ok": False, "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
