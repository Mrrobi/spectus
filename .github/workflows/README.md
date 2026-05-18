# GitHub Actions

## `test.yml` — CI

Runs on every push to `main` and every PR targeting `main`.
- Matrix: ubuntu / windows / macos × Python 3.12
- `uv sync --extra dev`
- `ruff check`
- `pytest tests/unit`
- Linux job also builds the wheel/sdist as a sanity check and uploads them as an artifact.

## `publish.yml` — release

Triggered by a tag push matching `v*.*.*`. Does:

1. **Guard** — confirms the tag matches `version` in `pyproject.toml`. Mismatch → fail fast.
2. **Test** — runs lint + unit tests on Linux.
3. **Build** — `uv build` produces wheel + sdist; uploads as workflow artifact.
4. **Publish to PyPI** — via PyPI Trusted Publisher (OIDC, no token).
5. **GitHub Release** — creates `vX.Y.Z` release with the wheel + sdist attached and auto-generated changelog.

### One-time setup on PyPI

To enable the Trusted Publisher OIDC flow:

1. Visit https://pypi.org/manage/project/spectus/settings/publishing/
2. Click **Add a new publisher** → **GitHub**.
3. Fill in:
   - Owner: `Mrrobi`
   - Repository name: `spectus`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`
4. Save.

Also create the `pypi` environment in GitHub repo settings → Environments → New → `pypi`. (Optional: add deployment-protection rule so only `v*.*.*` tags can deploy.)

### Cutting a release

```bash
# bump version in pyproject.toml first, e.g. 0.1.0 -> 0.1.1
git commit -am "Release 0.1.1"
git tag v0.1.1
git push origin main --tags
```

Workflow runs automatically. Tag → wheel built → published to PyPI → GitHub release created with binaries attached.

### Manual trigger

Workflow → Run workflow → pick branch. Useful for re-running a failed publish (PyPI version still must not exist).
