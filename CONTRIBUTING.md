# Contributing to spectus

Thanks for the interest. This document covers the local dev loop, conventions, and how releases happen. Issues, ideas, and PRs are welcome — read on for the shortest path.

---

## Table of contents

- [Develop from source](#develop-from-source)
- [Common commands](#common-commands)
- [Project layout](#project-layout)
- [Style + quality bars](#style--quality-bars)
- [How to write a new test](#how-to-write-a-new-test)
- [Where each kind of change goes](#where-each-kind-of-change-goes)
- [Commit messages](#commit-messages)
- [PR checklist](#pr-checklist)
- [CI](#ci)
- [Release flow](#release-flow)
- [Reporting bugs / requesting features](#reporting-bugs--requesting-features)
- [Code of conduct](#code-of-conduct)

---

## Develop from source

```bash
git clone https://github.com/Mrrobi/spectus
cd spectus

# install all deps incl. dev + notebook
uv sync --extra dev --extra notebook
uv run playwright install chromium
uv run alembic upgrade head

# add OpenAI key
cp .env.example .env
# edit .env -> OPENAI_API_KEY=sk-...
```

Requires Python **3.10+** and [uv](https://docs.astral.sh/uv/). Linux / macOS / Windows.

---

## Common commands

```bash
make test         # unit tests with coverage
make test-fast    # skip @browser-marked tests
make lint         # ruff check + format check
make format       # ruff fix + format
make typecheck    # mypy
make notebook     # JupyterLab on notebooks/personal.ipynb
make demo         # seed templates + run demo extraction
make clean        # drop local DB + artifacts + caches
```

Or directly: `uv run pytest tests/unit -q`, `uv run ruff check .`, `uv run mypy spectus`, `uv run spectus extract URL "..."`.

---

## Project layout

```
spectus/
  __init__.py      <- public API (Client, SyncClient, extract, __version__)
  client.py        <- public clients
  cli.py           <- argparse CLI entry
  config.py        <- pydantic-settings Settings
  errors.py        <- exception hierarchy
  logging.py       <- structlog setup
  _core/           <- 24 services (extractor, orchestrator, pipeline, planner, ...)
  _db/             <- SQLAlchemy models + repositories + session
  _llm/            <- OpenAI client + prompts
  _schemas/        <- Pydantic contracts
alembic/           <- DB migrations
tests/unit/        <- 52 unit tests, run offline in <1s
examples/          <- 5 runnable usage examples
notebooks/         <- JupyterLab personal notebook
scripts/           <- one-off scripts (seed_demo, record_fixture, ...)
.github/workflows/ <- CI + release workflows
```

Underscore-prefixed packages (`_core`, `_db`, `_llm`, `_schemas`) are **internal**. External consumers should only import from `spectus` itself (`from spectus import extract, Client, SyncClient`).

---

## Style + quality bars

- **Python 3.10+**, formatted by `ruff format`, linted by `ruff check`. Rules and ignores live in `pyproject.toml`.
- **Type annotations** on all new code. `mypy` runs in CI; aim for clean — pragmatic ignores allowed where typing third-party libs is impractical.
- **Tests required** for new behaviour. Fast, offline by default; mark anything that needs real Chromium with `@pytest.mark.browser`.
- **Pydantic v2 strict mode** on every LLM-facing schema (`extra="forbid"`, `frozen=True`).
- **No silent failures.** Errors raise typed exceptions from `spectus/errors.py`; soft failures (validation, partial extraction) propagate via `ExtractionResponse.status="partial_success" | "failed"` with a populated `message`.
- **Adding a Settings key** requires updating the `_SETTABLE_KEYS` allowlist in `spectus/client.py` so external callers can pass it via `settings={...}`.

---

## How to write a new test

Most tests live in `tests/unit/` and use plain `pytest`:

```python
# tests/unit/test_my_thing.py
from spectus._core.my_thing import my_function


def test_happy_path():
    result = my_function(input_x)
    assert result.value == expected
    assert result.errors == []


def test_edge_case():
    result = my_function("")
    assert result.value is None
```

Conventions:

- One file per module under test.
- Pure-function tests prefer no fixtures.
- Async tests: `pytest-asyncio` auto-mode is enabled, just write `async def test_...`.
- Tests that hit Chromium must be marked: `@pytest.mark.browser`.
- Tests that hit OpenAI: don't. Mock at the `LlmClient.json_call` level.

Run a single file:

```bash
uv run pytest tests/unit/test_my_thing.py -v
```

---

## Where each kind of change goes

| Change | Where |
|---|---|
| New extraction strategy | `spectus/_core/extraction_executor.py` (new `_exec_*` branch) + `spectus/_schemas/plan.py` (add to `ExtractionStrategy` literal) + planner prompt update |
| New field type | `spectus/_schemas/intent.py` `FieldType` literal + `spectus/_core/normalizer.py` + `spectus/_core/validator.py` (`_parses_as`) + `spectus/_core/merger.py` |
| New CLI subcommand | `spectus/cli.py` |
| New env var setting | `spectus/config.py` Settings + `spectus/client.py` `_SETTABLE_KEYS` |
| Tighten safety / compliance | `spectus/_core/compliance.py` |
| DB schema change | New alembic revision under `alembic/versions/`, plus matching `spectus/_db/models.py` update |
| Prompt tuning | `spectus/_llm/prompts.py` |

---

## Commit messages

Use the [Conventional Commits](https://www.conventionalcommits.org/) prefix:

```
feat:     new user-facing feature
fix:      bug fix
refactor: code change that doesn't add/remove behaviour
chore:    build, deps, tooling, version bumps
docs:     documentation only
test:     adding / fixing tests
ci:       CI / workflow changes
perf:     performance improvement
```

Example:

```
fix(executor): translate :contains() server-side, deepest-match wins

Earlier the selector with :contains() would crash the lexbor parser.
Now translated to base + Python text-filter; among matches, the element
with shortest text (= deepest container) is returned.
```

Bodies are optional but appreciated for non-trivial changes.

---

## PR checklist

Before opening a PR, confirm:

- [ ] `make lint` passes locally
- [ ] `make test` passes locally
- [ ] New/changed code has tests
- [ ] Public API changes are reflected in `README.md` or `EXAMPLES.md`
- [ ] Commit messages use Conventional-Commits prefixes
- [ ] No secrets in the diff (run `git diff --staged | grep -iE 'sk-|api.?key|token'`)

CI runs the same checks on Linux + Windows + macOS × Python 3.10–3.13. If anything fails, it fails the same way locally — easier to fix before opening the PR.

---

## CI

Every push to `main` and every PR runs `.github/workflows/test.yml`:

- Matrix: Ubuntu / Windows / macOS × Python 3.10 / 3.11 / 3.12 / 3.13
- `ruff check`
- `pytest tests/unit`
- Linux job also runs `uv build` and uploads wheel/sdist as an artifact

---

## Release flow

Releases are driven by git tags matching `v*.*.*`. The workflow at `.github/workflows/publish.yml` does:

1. **Guard** — checks tag matches `version` in `pyproject.toml` and `__version__` in `spectus/__init__.py`.
2. **Test** — `ruff` + `pytest` on Linux.
3. **Build** — `uv build` (wheel + sdist).
4. **Publish to PyPI** — via Trusted Publisher OIDC (no token in repo).
5. **GitHub release** — creates `vX.Y.Z` with auto-generated notes and the wheel + sdist attached.

### Cutting a release

```bash
# 1. bump version in pyproject.toml AND spectus/__init__.py
# 2. commit
git commit -am "chore: bump X.Y.Z"

# 3. tag + push
git tag vX.Y.Z
git push origin main --tags
```

PyPI versions are **immutable** — same version can never be re-uploaded. If a publish fails, fix on `main`, bump the next patch, retag.

### One-time PyPI setup (maintainer only)

PyPI side: `https://pypi.org/manage/project/spectus/settings/publishing/` → Add a new publisher → GitHub:

```
Owner:               Mrrobi
Repository name:     spectus
Workflow filename:   publish.yml
Environment name:    pypi
```

GitHub side: repo Settings → Environments → New → name `pypi`. Optional deployment-protection rule: only allow `v*.*.*` tags to deploy.

After this, no PyPI token ever lives in the repo or in chat — OIDC handles auth automatically.

---

## Reporting bugs / requesting features

Open an issue at `https://github.com/Mrrobi/spectus/issues`. Include:

- Python version (`python --version`)
- spectus version (`spectus version`)
- OS
- Minimal repro: the URL + instruction, or pasted code
- For extraction bugs: the relevant artifact bundle from `./artifacts/{job_id}/` (especially `compact.json`, `plan.json`, `validation.json`, `llm/*.json`) — these reveal exactly what the system saw and decided
- For OpenAI errors: model name (`OPENAI_MODEL_*`)

Don't include API keys, screenshots of pages behind a login, or anything you wouldn't want public.

---

## Code of conduct

Be excellent to each other. Disagree on technical points; never on people. Maintainers reserve the right to remove comments, PRs, or contributors that don't follow this.
