# Contract: Releases

| Step | Who | What |
|---|---|---|
| Once | Builder | On pypi.org, add a pending trusted publisher: project `loopbrake`, owner `SahilSelokar`, repository `LoopBrake`, workflow `publish.yml`, environment `pypi`. On GitHub, create the environment `pypi`. |
| Each release | Builder | Set `__version__` in `src/loopbrake/__init__.py`, commit, then `git tag vX.Y.Z && git push origin vX.Y.Z` |
| Each release | Workflow `build` | Checks the tag against the version, runs `uv build`, smoke-tests `loopbrake --version` from the wheel, and checks the wheel holds only `loopbrake/` and `*.dist-info/`. Uploads `dist/`. |
| Each release | Workflow `publish` | `environment: pypi`, `permissions: id-token: write`, `uv publish` |

**Guarantees**:
- No token is stored anywhere.
- A tag that doesn't match the version never publishes.
- The package contains no `eval/`, `specs/`, `tests/`, data or results.

**What users get**: `pip install loopbrake` or `uv add loopbrake`. With the toolkit adapter:
`pip install "loopbrake[agent-sdk]"`.
