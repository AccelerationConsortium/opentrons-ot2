# SonarQube Integration Plan

## Prerequisites

- SonarQube server (or SonarCloud) with a project created for this repo
- `SONAR_TOKEN` added as a GitHub Actions secret
- `SONAR_HOST_URL` added as a GitHub Actions secret (skip if using SonarCloud)

## 1. sonar-project.properties

Create in repo root:

```properties
sonar.projectKey=acceleration-consortium_opentrons-ot2
sonar.projectName=opentrons-ot2
sonar.sources=src
sonar.tests=tests
sonar.python.version=3.10
sonar.python.coverage.reportPaths=coverage.xml
```

## 2. New GitHub Actions workflow — .github/workflows/sonar.yml

Runs on push to main and on PRs. Generates coverage report then hands off to the SonarQube scanner.

```yaml
name: SonarQube Analysis

on:
  push:
    branches: [main]
  pull_request:

jobs:
  sonar:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # full history for blame/new-code detection

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync --group test

      - name: Run tests with coverage
        run: uv run pytest --cov=src --cov-report=xml

      - name: SonarQube Scan
        uses: SonarSource/sonarqube-scan-action@v5
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}  # omit if SonarCloud
```

## 3. pre-commit hook — sonar-scanner (optional local scan)

Add to `.pre-commit-config.yaml`. This is slow so mark it `stages: [manual]`
so it only runs when explicitly invoked (`pre-commit run sonar --hook-stage manual`),
not on every commit.

```yaml
  - repo: local
    hooks:
      - id: sonar
        name: SonarQube local scan
        language: system
        entry: sonar-scanner
        pass_filenames: false
        stages: [manual]
```

Requires `sonar-scanner` CLI installed locally. Most devs will rely on CI instead.

## 4. pyproject.toml — add pytest-cov

```toml
[project.optional-dependencies]
test = [
    "pytest",
    "pytest-asyncio",
    "pytest-cov",   # add this
    "pytest-cov",
]
```

And ensure coverage is configured:

```toml
[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*"]
```

## Open questions

- SonarCloud (managed, free for public repos) vs self-hosted SonarQube?
- Should the Sonar step block PRs (quality gate) or just report?
- Do we want to exclude the `io/_legacy_direct.py` file from analysis (already excluded from linting)?
