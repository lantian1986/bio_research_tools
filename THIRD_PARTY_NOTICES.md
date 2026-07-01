# Third-party notices

This repository adapts the `literature-review` workflow and PubMed retrieval
logic from the supplied Claude Science runtime release, whose skill declares
the Apache License 2.0.

The software sends user-provided literature queries or identifiers to these
public services:

- PubMed / NCBI E-utilities:
  https://www.ncbi.nlm.nih.gov/home/about/policies/
- Crossref REST API:
  https://www.crossref.org/documentation/retrieve-metadata/
- OpenAlex API:
  https://openalex.org/terms

Users remain responsible for complying with each upstream service's current
terms, privacy policy, attribution requirements, and rate limits. Optional
contact and API-key environment variables are not committed to this
repository.
