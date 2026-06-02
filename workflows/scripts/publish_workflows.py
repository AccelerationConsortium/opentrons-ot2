# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests>=2.34.1",
#     "python-dotenv>=1.2.2",
# ]
# ///
"""Deploy workflows to the UniteLabs platform.

A workflow is any top-level directory whose pyproject.toml declares
`[tool.unitelabs.workflow]`. This script zips the workflow directory plus
the sibling `shared/` library verbatim and POSTs/PATCHes the bundle to the
platform.

The PEP 723 header above declares this script's own runtime deps so
`uv run scripts/deploy.py …` resolves them into an ephemeral env without
needing a project pyproject.toml at the repo root.

Bundle layout — the workflow dir ships verbatim, `shared/` is vendored as a
flat package so `import shared.steps.X` resolves at bundle root:

    <bundle root>/
    ├── <wf-dir>/                ← e.g. w01-hello-world/
    │   ├── pyproject.toml       ← shipped as-is
    │   ├── uv.lock              ← shipped as-is
    │   └── src/<pkg>/           ← <pkg> = slug with `-` replaced by `_`
    │       ├── __init__.py
    │       ├── workflow.py      ← @flow lives here
    │       └── phase_*.py
    └── shared/                  ← contents of dev `shared/src/shared/`, hoisted
        ├── __init__.py
        ├── config/
        ├── steps/
        └── ...

Locally `shared` is a uv editable path dep with src-layout
(`shared/src/shared/...`); the platform doesn't install it (no PyPI counterpart),
so we vendor the package's source at the bundle root where Python's import
system can find it without any sys.path manipulation.

NOTE: the opinionated bits here — bundle vendoring of editable path deps and
direct-dep stitching from sibling pyprojects (see `resolve_dependencies` and
`build_bundle`) — are workarounds for current platform limits. The UniteLabs
API is expected to absorb both soon (server-side dep resolution from the
bundle's pyproject + native handling of `[tool.uv.sources]`), at which point
this script can be slimmed back down to a pure bundle-and-POST.

Entrypoint format (passed to the platform): `<wf-dir>/src/<pkg>/<file>:<func>`.
Workflows declare the short `<file>:<func>` form in pyproject; this script
prefixes the bundle path.

Usage:
    uv run scripts/deploy.py --all [--tag TAG ...]
    uv run scripts/deploy.py <workflow-slug> [--tag TAG ...]
    uv run scripts/deploy.py --git-tag <slug>/v<X.Y.Z> [--tag TAG ...]
    uv run scripts/deploy.py --changed-from <ref> [--tag TAG ...]
    uv run scripts/deploy.py --list [--changed-from <ref>]

<workflow-slug> is the `[project].name` from a workflow's pyproject.toml.

`--channel dev|stg|prd` layers on top of any of the above: it prepends
`[DEV] `/`[STG] `/`[PRD] ` to the platform display_name and adds the channel
name as a platform tag, so the same UniteLabs tenant can host parallel
DEV/STG/PRD records of each workflow.
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED_DIR = REPO_ROOT / "shared"

# Bundle exclusions. Everything dev-only or runtime-generated stays off the
# worker — tests/, runtime artifacts (logs/, checkpoints/), build caches.
EXCLUDED_DIRS = frozenset(
    {
        ".venv",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "tests",
        "logs",
        "checkpoints",
    }
)
EXCLUDED_NAMES = frozenset({".DS_Store", ".env", ".env.local"})


def discover_workflows() -> dict[str, Path]:
    """Map workflow slug (`[project].name`) → workflow directory.

    A workflow is any top-level directory whose pyproject.toml defines
    `[tool.unitelabs.workflow]`. Validates `.entrypoint` here so a malformed
    workflow fails fast, before we authenticate.
    """
    workflows: dict[str, Path] = {}
    for pp in REPO_ROOT.glob("*/pyproject.toml"):
        with pp.open("rb") as f:
            data = tomllib.load(f)
        meta = data.get("tool", {}).get("unitelabs", {}).get("workflow")
        if meta is None:
            continue
        slug = data["project"]["name"]
        if not meta.get("entrypoint"):
            msg = f"{slug}: missing [tool.unitelabs.workflow].entrypoint in {pp}"
            raise RuntimeError(msg)
        workflows[slug] = pp.parent
    return workflows


def _changed_paths(ref: str) -> list[str]:
    """Paths changed in `git diff --name-only <ref>..HEAD`, repo-root relative."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{ref}..HEAD"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def affected_workflows(changed_paths: list[str], workflows: dict[str, Path]) -> list[str]:
    """Workflow slugs affected by a set of changed paths.

    `shared/` is vendored into every bundle and `scripts/deploy.py` rewrites
    every bundle's contents, so a touch to either marks every workflow as
    affected. Otherwise a workflow is affected iff a changed path is under
    its directory.
    """
    if any(p.startswith("shared/") or p == "scripts/deploy.py" for p in changed_paths):
        return sorted(workflows.keys())
    affected: set[str] = set()
    for path in changed_paths:
        for slug, wf_dir in workflows.items():
            if path.startswith(f"{wf_dir.name}/"):
                affected.add(slug)
    return sorted(affected)


# Release tag form: `<slug>/v<X.Y.Z>` (slug = workflow's [project].name).
_RELEASE_TAG_RE = re.compile(r"^(?P<slug>[a-z][a-z0-9-]*)/(?P<version_label>v(?P<version>\d+\.\d+\.\d+))$")


def parse_release_tag(ref: str) -> tuple[str, str, str]:
    """Parse `<slug>/v<X.Y.Z>` into (slug, version_label, version).

    Accepts both short tag names (`w03-liquid-handling/v1.2.0`) and the
    `refs/tags/<...>` long form GitLab CI sometimes provides.
    """
    stripped = ref[len("refs/tags/") :] if ref.startswith("refs/tags/") else ref
    match = _RELEASE_TAG_RE.fullmatch(stripped)
    if not match:
        msg = (
            f"git tag {ref!r} doesn't match the per-workflow release pattern "
            f"`<slug>/v<X.Y.Z>` (e.g. `w03-liquid-handling/v1.2.0`)."
        )
        raise ValueError(msg)
    return match["slug"], match["version_label"], match["version"]


def load_identity(workflow_dir: Path) -> dict:
    """Read the workflow's identity from its pyproject.toml."""
    with (workflow_dir / "pyproject.toml").open("rb") as f:
        pp = tomllib.load(f)
    project = pp["project"]
    tool = pp.get("tool", {}).get("unitelabs", {}).get("workflow", {})
    return {
        "name": project["name"],
        "version": project["version"],
        "description": project.get("description", ""),
        "display_name": tool.get("display_name", project["name"]),
        "entrypoint": tool.get("entrypoint"),
        "tags": list(tool.get("tags", [])),
        "dependencies": list(project.get("dependencies", [])),
    }


_PKG_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+")


def _pkg_name(req: str) -> str:
    """Lowercased package name prefix of a PEP 508 requirement spec."""
    match = _PKG_NAME_RE.match(req.strip())
    return match.group(0).lower() if match else req.strip().lower()


def resolve_dependencies(workflow_dir: Path) -> list[str]:
    """Direct-dep list = workflow's deps ⨁ shared's deps, deduped, minus `shared`.

    The platform's `dependencies` API field drives the runtime venv install. We
    can't traverse the editable `shared = { path = "../shared" }` source on the
    server, so the deploy stitches both pyprojects' [project].dependencies arrays
    here and sends the merged direct-dep set. pip resolves transitives on the
    platform from this list.

    Workflow deps win on duplicates (more specific to the workflow's actual
    runtime). The local `shared` entry is dropped — it has no PyPI counterpart;
    shared/'s source is vendored at the bundle root by `build_bundle`.

    TODO: remove once the UniteLabs API resolves deps from the bundle's
    pyproject server-side (including [tool.uv.sources] path deps).
    """
    with (workflow_dir / "pyproject.toml").open("rb") as f:
        wf = tomllib.load(f)
    with (SHARED_DIR / "pyproject.toml").open("rb") as f:
        sh = tomllib.load(f)
    wf_deps = list(wf.get("project", {}).get("dependencies", []))
    sh_deps = list(sh.get("project", {}).get("dependencies", []))
    seen: dict[str, str] = {}
    for req in [*wf_deps, *sh_deps]:
        name = _pkg_name(req)
        if name == "shared":
            continue
        seen.setdefault(name, req)
    return list(seen.values())


def bundle_entrypoint(workflow_dir: Path, identity: dict) -> str:
    """Compute the bundle-root-relative entrypoint the platform expects.

    Workflows declare `<file>:<func>` (e.g. `workflow.py:hello_world_flow`).
    Convention: package dir under `<wf>/src/` is the slug with `-` replaced
    by `_` — matches `uv init --package` output.
    """
    pkg_name = identity["name"].replace("-", "_")
    pkg_dir = workflow_dir / "src" / pkg_name
    if not pkg_dir.is_dir():
        msg = (
            f"{identity['name']}: expected package directory {pkg_dir.relative_to(REPO_ROOT)} "
            f"(slug with `-` replaced by `_`) — not found"
        )
        raise RuntimeError(msg)
    rel, _, func = identity["entrypoint"].partition(":")
    if not rel or not func:
        msg = f"{identity['name']}: entrypoint {identity['entrypoint']!r} must be `<file>:<func>`"
        raise RuntimeError(msg)
    if not (pkg_dir / rel).is_file():
        msg = (
            f"{identity['name']}: entrypoint file {rel!r} not found at "
            f"{(pkg_dir / rel).relative_to(REPO_ROOT)} — fix [tool.unitelabs.workflow].entrypoint"
        )
        raise RuntimeError(msg)
    return f"{workflow_dir.name}/src/{pkg_name}/{rel}:{func}"


def _add_tree(zf: zipfile.ZipFile, src_root: Path, dst_root: Path) -> None:
    """Copy every file under src_root into zf, rooted at dst_root.

    Skips dev/build artifacts (`__pycache__`, `.venv`, `.DS_Store`, etc.).
    No content transformation — source bytes ship as-is. Exclusion match is
    against the path *relative to src_root* so an excluded name in an
    ancestor of src_root (e.g. a clone under ~/.venv/...) doesn't filter
    every file.
    """
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(src_root)
        if any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if src.name in EXCLUDED_NAMES:
            continue
        zf.write(src, str(dst_root / rel))


def build_bundle(workflow_dir: Path, identity: dict) -> Path:
    """Zip the workflow dir verbatim and vendor `shared/` as a flat package.

    - Workflow dir ships rooted at its own name (the platform sees the same
      paths the developer does).
    - `shared/src/shared/` is hoisted to `shared/` at bundle root so
      `import shared.steps.X` resolves directly. We drop the src-layout
      scaffolding (`shared/pyproject.toml`, `shared/uv.lock`,
      `shared/src/...`) because the platform doesn't install `shared` —
      its deps are stitched into the workflow's dep list via
      `resolve_dependencies`.

    TODO: remove the vendoring step once the platform installs editable path
    deps from the bundle's pyproject directly.
    """
    bundle_path = Path(tempfile.gettempdir()) / f"{identity['name']}_v{identity['version']}.zip"
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        _add_tree(zf, workflow_dir, Path(workflow_dir.name))
        _add_tree(zf, SHARED_DIR / "src" / "shared", Path("shared"))
    return bundle_path


def authenticate(auth_url: str, client_id: str, client_secret: str) -> str:
    response = requests.post(
        auth_url.rstrip("/") + "/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def find_existing_workflow(client: requests.Session, base_url: str, display_name: str) -> str | None:
    """Look up workflow by display_name. Paginated; refuses to deploy on duplicates.

    Server-side name filter is unreliable, so we list and match client-side.
    Paginates with `_skip + _take` so a server cap on `_take` can't silently
    truncate (a missed match would cause us to recreate the workflow as a
    duplicate). Hard-fails when multiple records share the same display_name —
    picking one risks overwriting the wrong record.

    Soft-deleted workflows (the UI "delete" only flips `enabled=false`) are
    still returned; the metadata PATCH later forces `enabled=true` so a
    redeploy resurrects rather than updating a hidden record.
    """
    matches: list[str] = []
    skip, page_size = 0, 100
    while True:
        response = client.get(
            f"{base_url}v1/workflows",
            params={"_take": page_size, "_skip": skip},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload["data"]
        matches.extend(wf["id"] for wf in data if wf["name"] == display_name)
        skip += len(data)
        if not data or skip >= payload["pagination"]["totalCount"]:
            break
    if len(matches) > 1:
        msg = (
            f"Multiple workflows named {display_name!r} on the platform: {matches}. "
            f"Refusing to deploy — resolve the duplicate in the UI first."
        )
        raise RuntimeError(msg)
    return matches[0] if matches else None


def deploy_one(
    workflow_dir: Path,
    *,
    base_url: str,
    token: str,
    extra_tags: list[str],
    channel: str | None = None,
) -> None:
    identity = load_identity(workflow_dir)
    if channel:
        # Single-tenant deploys: prefix display_name so DEV/STG/PRD records
        # coexist as distinct platform entries. Also tag with the channel name
        # for filtering in the UI.
        identity["display_name"] = f"[{channel.upper()}] {identity['display_name']}"
        extra_tags = [*extra_tags, channel]
    entrypoint = bundle_entrypoint(workflow_dir, identity)

    print(f"\n--- {identity['display_name']} (v{identity['version']}) ---")
    print("Building bundle...")
    bundle_path = build_bundle(workflow_dir, identity)
    print(f"  bundle:   {bundle_path} ({bundle_path.stat().st_size // 1024} KB)")
    print(f"  entry:    {entrypoint}")

    all_tags = sorted(set(identity["tags"]) | set(extra_tags))

    with requests.Session() as client:
        client.headers.update({"Authorization": f"Bearer {token}"})
        existing_id = find_existing_workflow(client, base_url, identity["display_name"])
        if existing_id:
            print(f"Updating workflow id={existing_id}")
            with bundle_path.open("rb") as fh:
                response = client.patch(
                    f"{base_url}v1/workflows/{existing_id}",
                    files={"file": (bundle_path.name, fh, "application/zip")},
                    data={"entrypoint": entrypoint},
                    timeout=120,
                )
            response.raise_for_status()
            workflow_id = existing_id
        else:
            print("Creating workflow")
            with bundle_path.open("rb") as fh:
                response = client.post(
                    f"{base_url}v1/workflows",
                    files={"file": (bundle_path.name, fh, "application/zip")},
                    data={
                        "name": identity["display_name"],
                        "entrypoint": entrypoint,
                        "description": identity["description"],
                    },
                    timeout=120,
                )
            response.raise_for_status()
            workflow_id = response.json()["id"]
            print(f"  created: id={workflow_id}")

        print("Patching metadata...")
        # `dependencies` is the install-time requirements list the platform uses
        # to provision the worker venv. We send the stitched set from the
        # workflow's + shared's [project].dependencies (deduped, workflow wins)
        # so the platform doesn't have to traverse [tool.uv.sources] or the
        # editable `shared` path dep itself. `shared` is dropped because it has
        # no PyPI counterpart; its source is vendored at the bundle root by
        # `build_bundle`. `version` is omitted because the API rejects unknown
        # fields. `enabled: True` is forced because the UI "delete" only flips
        # enabled=false; without this, redeploying a "deleted" workflow silently
        # updates a hidden record.
        resolved_deps = resolve_dependencies(workflow_dir)
        deps_summary = " ".join(resolved_deps)
        print(f"  resolved deps: {len(resolved_deps)} packages ({len(deps_summary)} chars)")
        response = client.patch(
            f"{base_url}v1/workflows/{workflow_id}",
            json={
                "description": identity["description"],
                "dependencies": deps_summary,
                "tags": all_tags,
                "enabled": True,
            },
            timeout=60,
        )
        if response.status_code >= 400:
            print(f"  API {response.status_code}: {response.text[:500]}")
        response.raise_for_status()

    bundle_path.unlink(missing_ok=True)
    print(f"Deployed: {identity['display_name']} v{identity['version']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy workflows to the UniteLabs platform.")
    parser.add_argument(
        "workflow",
        nargs="?",
        help="Workflow slug ([project].name). Omit if --all or --git-tag is set.",
    )
    parser.add_argument("--all", action="store_true", help="Deploy every workflow in the repo.")
    parser.add_argument(
        "--git-tag",
        dest="git_tag",
        help=(
            "Release tag `<slug>/v<X.Y.Z>`. Dispatches to that single workflow, "
            "verifies its [project].version matches `<X.Y.Z>`, and adds `v<X.Y.Z>` "
            "to the platform tags. Intended for CI on tag pushes."
        ),
    )
    parser.add_argument(
        "--tag",
        "-t",
        action="append",
        default=[],
        help="Extra platform tag (repeatable). Stacks with --git-tag's version label.",
    )
    parser.add_argument(
        "--channel",
        choices=["dev", "stg", "prd"],
        help=(
            "Deploy channel. Prefixes display_name with `[DEV] `/`[STG] `/`[PRD] ` "
            "and adds the channel name as a platform tag, so a single tenant can "
            "host parallel DEV/STG/PRD records of the same workflow."
        ),
    )
    parser.add_argument(
        "--changed-from",
        dest="changed_from",
        metavar="REF",
        help=(
            "Deploy only workflows affected by `git diff --name-only <REF>..HEAD`. "
            "A touch under `shared/` or to `scripts/deploy.py` marks every workflow "
            "as affected. Mutually exclusive with a positional workflow slug and "
            "--git-tag."
        ),
    )
    parser.add_argument(
        "--list",
        dest="list_only",
        action="store_true",
        help=(
            "Print the selected workflow slugs (one per line) and exit. Skips auth "
            "and deploy. With --changed-from, prints affected slugs; alone, prints "
            "every discovered workflow."
        ),
    )
    args = parser.parse_args()

    if args.workflow and (args.all or args.git_tag or args.changed_from):
        parser.error("workflow slug cannot be combined with --all, --git-tag, or --changed-from")
    if args.git_tag and (args.all or args.changed_from):
        parser.error("--git-tag cannot be combined with --all or --changed-from")

    workflows = discover_workflows()
    if not workflows:
        print(f"No workflows found under {REPO_ROOT}", file=sys.stderr)
        return 1

    # --list short-circuits before env + auth so PR-validate CI can run it
    # without secrets.
    if args.list_only:
        if args.changed_from:
            slugs = affected_workflows(_changed_paths(args.changed_from), workflows)
        elif args.workflow:
            if args.workflow not in workflows:
                print(f"Workflow not found: {args.workflow!r}", file=sys.stderr)
                return 1
            slugs = [args.workflow]
        elif args.git_tag:
            try:
                slug, _, _ = parse_release_tag(args.git_tag)
            except ValueError as e:
                print(str(e), file=sys.stderr)
                return 1
            slugs = [slug] if slug in workflows else []
        else:
            slugs = sorted(workflows.keys())
        for slug in slugs:
            print(slug)
        return 0

    if not (args.all or args.workflow or args.git_tag or args.changed_from):
        parser.print_usage(sys.stderr)
        print(
            f"{parser.prog}: error: specify one of: workflow slug, --all, --git-tag <ref>, or --changed-from <ref>",
            file=sys.stderr,
        )
        print("\nAvailable workflows:", file=sys.stderr)
        for slug in sorted(workflows):
            print(f"  {slug}", file=sys.stderr)
        return 1

    load_dotenv(REPO_ROOT / ".env")
    required_env = ("BASE_URL", "AUTH_URL", "CLIENT_ID", "CLIENT_SECRET")
    missing = [k for k in required_env if not os.environ.get(k)]
    if missing:
        print(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            f"Set them in {REPO_ROOT / '.env'} or your shell.",
            file=sys.stderr,
        )
        return 1
    base_url = os.environ["BASE_URL"].rstrip("/") + "/"
    auth_url = os.environ["AUTH_URL"]
    client_id = os.environ["CLIENT_ID"]
    client_secret = os.environ["CLIENT_SECRET"]

    extra_tags = list(args.tag)

    if args.git_tag:
        try:
            slug, version_label, version = parse_release_tag(args.git_tag)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            return 1
        if slug not in workflows:
            print(
                f"git tag {args.git_tag!r} references unknown workflow {slug!r}.",
                file=sys.stderr,
            )
            print(f"Available: {sorted(workflows)}", file=sys.stderr)
            return 1
        identity = load_identity(workflows[slug])
        if identity["version"] != version:
            print(
                f"git tag {args.git_tag!r} expects version {version!r}, but "
                f"{workflows[slug].name}/pyproject.toml declares {identity['version']!r}. "
                f"Bump [project].version before tagging (or fix the tag).",
                file=sys.stderr,
            )
            return 1
        targets = [workflows[slug]]
        extra_tags.append(version_label)
        print(f"Releasing {slug} at {version_label}")
    elif args.changed_from:
        affected = affected_workflows(_changed_paths(args.changed_from), workflows)
        if not affected:
            print(f"No workflows affected by changes since {args.changed_from!r}.")
            return 0
        print(f"Affected workflows since {args.changed_from!r}: {', '.join(affected)}")
        targets = [workflows[slug] for slug in affected]
    elif args.all:
        targets = list(workflows.values())
    else:
        if args.workflow not in workflows:
            print(f"Workflow not found: {args.workflow!r}", file=sys.stderr)
            print(f"Available: {sorted(workflows)}", file=sys.stderr)
            return 1
        targets = [workflows[args.workflow]]

    print("Authenticating...")
    token = authenticate(auth_url, client_id, client_secret)
    print(f"  token length: {len(token)}")

    for workflow_dir in targets:
        deploy_one(
            workflow_dir,
            base_url=base_url,
            token=token,
            extra_tags=extra_tags,
            channel=args.channel,
        )

    print("\nDeployment complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
