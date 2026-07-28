"""Every third-party import must be declared in requirements.txt.

This exists because of a real failure: the API's dependencies were pip-installed
locally but left commented out in requirements.txt. Every test passed, the
container built cleanly, and it died on start with `uvicorn: not found` — a
failure that only appears in a deployed environment, where the feedback loop is
minutes long and the error names a symptom rather than a cause.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Import name -> distribution name, where they differ.
DISTRIBUTION = {
    "dotenv": "python-dotenv",
    "sse_starlette": "sse-starlette",
    "langgraph": "langgraph",
    "yaml": "pyyaml",
}

# Shipped with the interpreter or pulled in transitively by a declared package.
NOT_DECLARED = {"langchain_core"}


def _third_party_imports(*roots: str) -> set[str]:
    found: set[str] = set()
    for root in roots:
        for path in (ROOT / root).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    found.add(node.module.split(".")[0])

    local = {p.name for p in ROOT.iterdir()}
    return {
        name
        for name in found
        if name not in sys.stdlib_module_names
        and name not in local
        and name not in NOT_DECLARED
    }


def test_runtime_imports_are_declared_in_requirements():
    declared = {
        line.split("[")[0].split(">")[0].split("=")[0].strip().lower()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    imported = _third_party_imports("elfagent", "api")
    missing = {
        name
        for name in imported
        if DISTRIBUTION.get(name, name).lower() not in declared
    }

    assert not missing, (
        f"imported but not in requirements.txt: {sorted(missing)}. "
        "The container installs only what is declared there, so this builds "
        "cleanly and fails at startup."
    )


def test_the_container_entrypoint_is_installable():
    """The Dockerfile's CMD runs uvicorn; it has to be in the image."""
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf8")

    assert "uvicorn" in dockerfile, "the entrypoint changed; update this test"
    assert any(
        line.strip().startswith("uvicorn")
        for line in requirements.splitlines()
    ), "Dockerfile starts uvicorn but requirements.txt does not install it"


def test_the_warehouse_is_not_built_into_the_volume_mount_path():
    """A mounted volume replaces the directory, taking the warehouse with it."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf8")

    assert "ELFAGENT_WAREHOUSE=/app/warehouse" in dockerfile
    assert "ELFAGENT_CHECKPOINTS=/app/data" in dockerfile, (
        "checkpoints are runtime state and belong on the volume; the warehouse "
        "is a build artefact and must not share that path"
    )
