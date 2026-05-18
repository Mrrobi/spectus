# Contributing to spectus

Thanks for the interest. This file describes the local dev loop, conventions, and how releases happen.

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

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

### Common commands

```bash
make test         # unit tests with coverage
make test-fast    # skip @browser-marked tests
make lint         # ruff check + format check
make format       # ruff fix + format
make typecheck    # mypy strict
make notebook     # JupyterLab on notebooks/personal.ipynb
make demo         # seed templates + run demo extraction
make clean        # drop local DB + artifacts + caches
```

### Project layout

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

Underscore-prefixed packages (`_core`, `_db`, `_llm`, `_schemas`) are internal — public consumers should import only from `spectus` itself.

---

## Style + quality bars

- **Python 3.12+**, formatted by `ruff format`, linted by `ruff check` with `E, F, I, B, UP, PL, SIM, RUF` rule sets (see `pyproject.toml` for ignores).
- **Type-strict** via mypy. New service modules must pass `mypy --strict`.
- **Tests required** for new behaviour. Aim for fast, offline tests; mark anything that touches real Chromium with `@pytest.mark.browser`.
- **Pydantic v2 strict mode** on all LLM-facing schemas (`extra="forbid"`, `frozen=True`). Adding a Settings key needs the allowlist in `spectus/client.py` updated.

---

## CI

Every push to `main` and every PR runs `.github/workflows/test.yml`:

- Matrix: Ubuntu / Windows / macOS × Python 3.12
- `ruff check`
- `pytest tests/unit`
- Linux job also runs `uv build` as a sanity check, uploads wheel/sdist as artifact

---

## Release flow

Releases are driven by git tags matching `v*.*.*`. The workflow at `.github/workflows/publish.yml` does:

1. **Guard** — checks tag matches `version` in `pyproject.toml` (and `spectus/__init__.py`'s `__version__`).
2. **Test** — `ruff` + `pytest` on Linux.
3. **Build** — `uv build` (wheel + sdist).
4. **Publish to PyPI** — via Trusted Publisher OIDC (no token in repo).
5. **GitHub release** — creates `vX.Y.Z` with auto-generated notes and the wheel + sdist attached.

To cut a release:

```bash
# 1. bump version in pyproject.toml AND spectus/__init__.py
# 2. commit
git commit -am "Release X.Y.Z"

# 3. tag + push
git tag vX.Y.Z
git push origin main --tags
```

If the workflow fails: fix on `main`, bump to the next patch (PyPI versions are immutable), retag, push.

### Trusted Publisher setup (one-time)

PyPI side: `https://pypi.org/manage/project/spectus/settings/publishing/` → Add a new publisher → GitHub.

```
Owner:               Mrrobi
Repository name:     spectus
Workflow filename:   publish.yml
Environment name:    pypi
```

GitHub side: repo Settings → Environments → New → name `pypi`. Optional deployment-protection rule: only allow `v*.*.*` tags to deploy.

After this, you never paste a PyPI token again.

---

## Reporting bugs / requesting features

Open an issue at `https://github.com/Mrrobi/spectus/issues`. Include:

- Python version (`python --version`)
- spectus version (`spectus version`)
- OS
- Minimal repro (URL + instruction, or pasted code)
- Relevant artifact bundle from `./artifacts/{job_id}/` for extraction bugs
