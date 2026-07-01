# Codex CLI Skill Migration Plan

## Goal

Make one migrated skill, `literature-review`, directly usable from Codex CLI in this repository.

The current package is a `darwin-arm64` runtime release, not a source project. It should not be ported wholesale. This migration extracts only the literature-review workflow, a minimal project-scoped PubMed MCP server, and the Crossref/OpenAlex helpers required to preserve DOI verification, retraction checks, and citation expansion.

## Main Assessment

- `skills/` is valuable as procedural knowledge and workflow guidance.
- `mcp-servers/` is valuable as the executable tool layer.
- `web-dist/`, `agents/`, `drizzle/`, `writetrace/`, `sharp-runtime/`, and platform binaries should not be directly migrated.
- The target is a repository-scoped Codex skill plus project MCP configuration, not a distributable plugin.
- All skills and MCP servers unrelated to `literature-review` are out of scope for this milestone.
- PubMed provides biomedical search and article metadata; Crossref verifies DOI metadata and retractions; OpenAlex provides citation-graph expansion.

## Target Shape

Recommended structure:

```text
repository/
├── .agents/
│   └── skills/
│       └── literature-review/
│           ├── SKILL.md
│           └── scripts/
│               └── literature_helpers.py
├── .codex/
│   └── config.toml
├── mcp-servers/
│   └── pubmed/
├── scripts/
│   └── start-pubmed-mcp
├── tests/
├── pixi.toml
├── pixi.lock
└── pyproject.toml
```

## Migration Steps

1. Inventory reusable assets.
   - Initialize this workspace as a Git repository and commit the untouched migration plan and source-release inventory as the baseline.
   - Inspect `skills/literature-review/SKILL.md` and its `kernel.py`.
   - Inventory only the PubMed MCP modules used by this skill.
   - Mark runtime-injected helpers, platform binaries, and unrelated assets as non-migratable.

2. Define the repository-scoped Codex shape.
   - Place the migrated skill at `.agents/skills/literature-review/SKILL.md` so Codex CLI can discover it from this repository.
   - Register the local stdio PubMed server under `[mcp_servers.pubmed]` in `.codex/config.toml`.
   - Do not create `.mcp.json`, `.codex-plugin/plugin.json`, a marketplace, or a nested plugin directory.
   - Treat `.codex/config.toml` as the single source of truth for the server command, environment forwarding, timeouts, and tool policy.
   - Require the repository to be trusted before project-scoped MCP configuration is used.
   - Do not migrate any original agents or additional skills.

3. Rebuild dependency and environment management with Pixi.
   - Use `pixi.toml` as the environment manifest and commit the generated `pixi.lock`.
   - Use `pyproject.toml` to describe the Python package itself; do not duplicate dependency ownership unnecessarily.
   - Support only `linux-64` in the first milestone. Add `osx-arm64` after the MVP passes.
   - Pin the Python runtime and declare both Conda and PyPI dependencies through Pixi.
   - Do not reuse macOS binaries, the original shared Conda environment, or dependency pins from unavailable runtime registries.
   - Define Pixi tasks for MCP startup, tests, linting, and manifest validation.
   - Run project commands through `pixi run --frozen` so normal execution never rewrites `pixi.lock`.
   - Document Pixi as a repository prerequisite and make launcher failures explicit when `pixi` is unavailable.
   - Confirm a clean `pixi install --locked` succeeds.

4. Package the PubMed MCP server.
   - Keep the original runtime release unchanged; make all modifications in the migrated PubMed copy under `mcp-servers/pubmed/`.
   - Expose only the three tools required by `literature-review`:
     - `search_articles`
     - `get_article_metadata`
     - `find_related_articles`
   - Remove unused tool schemas and handlers from the migrated server instead of relying only on a user-side allow list.
   - Decouple only the migrated PubMed copy from `mcp_servers_common.gate` and the global `mcp_bio` data files.
   - Preserve the gate's serialized-dispatch behavior in a PubMed-local policy module so shared HTTP clients are not called concurrently.
   - Keep the original `gate.py`, `mcp_bio/domains.json`, and `mcp_bio/deferred.json` as read-only references for future MCP migrations.
   - Extract and package the dependency closure for those three tools:
     - `mcp_pubmed`
     - `mcp_servers_common`
     - `pubmed_fetch`
     - `pubmed_search`
     - `ncbi_elink`
   - Trace imports and add any further shared modules discovered during packaging.
   - Add an import smoke test that loads every module in this dependency closure from a clean Pixi environment.
   - Add a Pixi task such as `pubmed-mcp` that launches the server with Python from the Pixi environment.
   - Add a launcher that resolves paths relative to the repository root, writes protocol messages only to stdout, and sends diagnostics only to stderr.
   - Register the launcher as a project-scoped stdio MCP server in `.codex/config.toml`.
   - Forward only documented optional environment variables such as `NCBI_EMAIL` and `NCBI_API_KEY`; never put secrets in project configuration.
   - Add concise MCP server `instructions` describing citation requirements, rate limits, and the recommended search-then-fetch workflow. Keep the first 512 characters self-contained.

5. Migrate the literature-review skill.
   - Convert `skills/literature-review/SKILL.md` to Codex skill format.
   - Remove Claude Science-specific tool assumptions such as `host.mcp()`, `save_artifacts`, `manage_environments`, and product-specific artifact language.
   - Replace runtime-injected helpers and the unavailable `host` module with normal scripts or importable Python modules.
   - Preserve and test the existing Crossref/OpenAlex behavior:
     - DOI lookup and verification through Crossref and doi.org
     - retraction metadata checks through Crossref
     - backward and forward citation expansion through OpenAlex
   - Expose these helpers through an explicit CLI instead of relying on host auto-loading:
     - `pixi run literature-helper verify-dois <input.json>`
     - `pixi run literature-helper expand-citations <input.json>`
     - `pixi run literature-helper crossref-lookup <input.json>`
   - Define versioned JSON input/output schemas, write results only to stdout, and send diagnostics only to stderr.
   - Use a generic, documented User-Agent and an optional contact email environment variable instead of the original host contact API.
   - Replace them with Codex CLI workflows:
     - workspace files for outputs
     - Pixi tasks plus Python for computation
     - the bundled PubMed MCP server for literature retrieval
     - concise references under `references/` for long instructions

6. Build the minimal working version.
   - Include one repository skill at `.agents/skills/literature-review`.
   - Include one project MCP entry at `.codex/config.toml`.
   - Include `pixi.toml`, a committed `pixi.lock`, and one cleanly installable environment.
   - Include one working MCP server: PubMed.
   - Run `pixi install --locked` as an explicit installation step.
   - Use `pixi run --frozen pubmed-mcp` only after the environment is installed; MCP startup must not perform dependency resolution or rewrite the lock file.
   - Measure warm MCP startup and keep it within Codex's configured startup timeout.
   - Restart Codex if skill or MCP configuration changes are not detected.
   - Confirm Codex CLI can discover the repository skill, start the project MCP server, and complete one real task.

7. Validate the P0 milestone.
   - Confirm the Git baseline exists and generated environments or secrets are ignored.
   - Validate skill frontmatter and structure.
   - Validate `.codex/config.toml`.
   - Run `pixi install --locked` in a clean checkout.
   - Start the MCP server through `pixi run --frozen pubmed-mcp`.
   - Complete the MCP initialization handshake and inspect the tool listing instead of treating a running process as sufficient.
   - Confirm exactly three PubMed tools are exposed and each has a stable name, description, JSON input schema, bounded output, and actionable error response.
   - Start Codex from the trusted repository and confirm `/skills` lists `literature-review` and `/mcp` reports PubMed.
   - Explicitly invoke `$literature-review` to verify skill loading.
   - Run one real task that searches recent biomedical papers, fetches PMID metadata, verifies DOI metadata, expands citations, and produces a grounded summary.
   - Test each helper CLI with valid input, malformed JSON, upstream failure, and empty results.

8. Validate P1 hardening after P0 passes.
   - Add `osx-arm64` to Pixi and verify the same locked environment and tests.
   - Test offline behavior, upstream rate limits, missing Pixi, missing optional contact/API-key variables, cancellation, and tool timeouts.
   - Verify the server remains responsive while a slow upstream request is in progress.
   - Confirm project configuration can disable the server, restrict enabled tools, and change approval modes.

9. Clean up the migrated project.
   - Exclude unrelated release artifacts:
     - `web-dist/`
     - `drizzle/`
     - `writetrace/`
     - `sharp-runtime/`
     - `__MACOSX/`
     - bundled platform binaries
   - Keep skill prompts concise.
   - Move long domain instructions into `references/`.
   - Keep the PubMed MCP server independently runnable and testable.
   - Preserve the original Apache-2.0 license and relevant third-party service notices for PubMed, Crossref, and OpenAlex.

## MCP Integration Rules

- Use stdio transport for the project-local PubMed server. Streamable HTTP is reserved for a separately deployed remote service.
- Project-level `.codex/config.toml` is the single source of truth for the server command and arguments.
- The stdio process must keep stdout protocol-clean; logs, warnings, and Pixi diagnostics go to stderr.
- The server must advertise useful initialization `instructions`, with the most important operating guidance in the first 512 characters.
- Secrets are accepted through named environment variables and are never committed to `.codex/config.toml`, `pixi.toml`, or examples.
- Startup and tool execution limits must be tested. Document a larger development `startup_timeout_sec` if first-time Pixi environment creation exceeds Codex's default startup window.
- The project controls enablement and tool policy through `.codex/config.toml`:

```toml
[mcp_servers.pubmed]
command = "pixi"
args = ["run", "--frozen", "pubmed-mcp"]
enabled = true
default_tools_approval_mode = "auto"
enabled_tools = [
  "search_articles",
  "get_article_metadata",
  "find_related_articles",
]
```

- Expose only the three tools needed by `literature-review`; adding another tool requires a new dependency and integration review.

## Recommended First Milestone

Create one repository-scoped Codex CLI skill with:

- `.agents/skills/literature-review`
- three PubMed MCP tools and their dependency closure
- `pixi.toml` and committed `pixi.lock`
- a `pubmed-mcp` Pixi task
- migrated Crossref/OpenAlex helper functions
- one project-scoped stdio MCP registration in `.codex/config.toml`
- server instructions and documented environment variables

The P0 milestone is complete when a clean `linux-64` checkout can run `pixi install --locked`, Codex started from the trusted repository can discover `literature-review`, `/mcp` exposes exactly three PubMed tools, and the skill can produce a grounded literature summary using real PubMed records plus verified Crossref/OpenAlex evidence.
