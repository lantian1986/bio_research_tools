from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "mcp-servers/pubmed/server.py"


def load_server():
    spec = importlib.util.spec_from_file_location("pubmed_server", SERVER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tool_registry_is_minimal() -> None:
    server = load_server()
    assert set(server.mcp._tool_manager._tools) == {
        "search_articles",
        "get_article_metadata",
        "find_related_articles",
    }


def test_parse_pubmed_xml() -> None:
    server = load_server()
    records = server.parse_pubmed_xml(
        """
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>123</PMID>
              <Article>
                <ArticleTitle>A useful result</ArticleTitle>
                <Abstract><AbstractText>Evidence.</AbstractText></Abstract>
                <AuthorList>
                  <Author><ForeName>Ada</ForeName><LastName>Lovelace</LastName></Author>
                </AuthorList>
                <Journal>
                  <Title>Example Journal</Title>
                  <JournalIssue><PubDate><Year>2024</Year></PubDate></JournalIssue>
                </Journal>
              </Article>
            </MedlineCitation>
            <PubmedData>
              <ArticleIdList>
                <ArticleId IdType="pubmed">123</ArticleId>
                <ArticleId IdType="doi">10.1000/example</ArticleId>
              </ArticleIdList>
            </PubmedData>
          </PubmedArticle>
        </PubmedArticleSet>
        """
    )
    assert records == [
        {
            "identifiers": {"pmid": "123", "doi": "10.1000/example"},
            "title": "A useful result",
            "abstract": "Evidence.",
            "authors": ["Ada Lovelace"],
            "journal": "Example Journal",
            "publication_date": {"year": "2024"},
            "doi_url": "https://doi.org/10.1000/example",
        }
    ]


def test_related_results_exclude_seed() -> None:
    server = load_server()
    groups = server.parse_related(
        {
            "linksets": [
                {
                    "ids": ["123"],
                    "linksetdbs": [
                        {
                            "linkname": "pubmed_pubmed",
                            "links": ["123", "456", "789"],
                        }
                    ],
                }
            ]
        },
        ["123"],
        1,
    )
    assert groups == [{"seed_pmids": ["123"], "related_pmids": ["456"]}]
