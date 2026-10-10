"""Enforce the package/domain boundaries of the ``janito`` codebase (issue #90).

Every module in ``janito/`` is assigned to a **domain**: the root package
(``janito`` and its top-level modules) or one of the subpackages
(``acp``, ``llm_adapters``, ``cli``, ``llm_clients``, ``mcp_client``,
``providers``, ``shell``, ``tooling``, ``tools``, ``ui``, ``web``).  This test statically
parses every import in the codebase (lazy imports inside functions included,
since the agent loop relies on them) and fails on any directed cross-domain
edge that is not in the allowed matrix below.

The matrix encodes the intended layering:

- the **outer** presentation / entry layers (``ui``, ``shell``, ``cli``,
  ``web``, ``acp``) may depend on anything below them; ``acp`` is a thin
  async entry layer over the web loop (it targets ``web`` + ``root`` only);
- ``llm_clients`` depends one-way on the shared adapter layer
  (``llm_adapters``) and on ``tooling`` / ``providers`` / the root config
  layer;
- ``llm_adapters`` is the shared per-API adapter layer (depended-on by
  ``llm_clients``, ``ui`` and ``web``); it must never import from
  ``llm_clients``;
- the **web** loop builds on the shared adapters only: like ``llm_adapters``
  it must never import from ``llm_clients`` -- every per-API piece the web
  needs (kwargs builders, accumulators, endpoint-routing helpers) lives in
  ``llm_adapters``;
- ``tooling`` is the tool framework, depended-on by ``tools`` (never the
  other way round);
- ``providers`` and the root config stores are leaves.

The remaining cycles -- root <-> providers -- are accepted and documented at
each lazy import site (see the ``issue #90`` comments); any *new* cycle or
wrong-direction edge fails this test.
"""

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PACKAGE_DIR = REPO_ROOT / "janito"

DOMAINS = {
    "acp",
    "cli",
    "llm_adapters",
    "llm_clients",
    "mcp_client",
    "providers",
    "root",
    "shell",
    "tooling",
    "tools",
    "ui",
    "web",
}

# Allowed directed cross-domain edges (source -> targets).  Same-domain
# imports are always allowed.  ``root`` is the composition/config hub: the
# entry point (``__main__``) dispatches to every mode, and the root service
# modules (config stores, system prompt, plugin manager, MCP manager) reach
# into the packages lazily.
ALLOWED_EDGES: dict[str, set[str]] = {
    "root": {"acp", "cli", "mcp_client", "providers", "shell", "tooling", "tools", "web"},
    "acp": {"root", "web"},
    "llm_adapters": {"providers"},
    "llm_clients": {"llm_adapters", "providers", "root", "tooling"},
    "mcp_client": set(),
    "providers": {"root"},
    "shell": {"llm_clients", "providers", "root", "tooling", "tools"},
    "tooling": {"root"},
    "tools": {"providers", "root", "tooling"},
    "ui": {"llm_adapters", "llm_clients", "providers", "root", "tooling"},
    "cli": {"llm_clients", "providers", "root", "shell", "tooling", "tools", "ui"},
    "web": {"llm_adapters", "providers", "root", "tooling", "tools"},
}


def _domain_of(module: str) -> str:
    """Map an absolute ``janito.*`` module name to its domain.

    Only the real subpackages are domains: ``janito.<pkg>`` /
    ``janito.<pkg>.<sub>`` -> ``<pkg>``; every top-level module
    (``janito.config_keys``, ``janito`` itself, ...) is ``root``.
    """
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "janito" and parts[1] in DOMAINS:
        return parts[1]
    return "root"


def _resolve_target(package_parts: list[str], level: int, module: str | None) -> str | None:
    """Resolve an ImportFrom target to an absolute module name."""
    if level == 0 and module:
        return module
    # Relative import: drop (level - 1) leading package components, then
    # append the module.  ``from .x`` (level 1) keeps the package;
    # ``from ..x`` (level 2) drops one leading component, etc.
    package_parts = package_parts[: len(package_parts) - (level - 1)]
    if module:
        package_parts.append(module)
    return ".".join(package_parts)


def _imports_of(source_file: Path) -> list[tuple[int, str, str]]:
    """Return ``(lineno, source_module, target_module)`` for every import."""
    rel_parts = source_file.relative_to(REPO_ROOT).with_suffix("").parts
    if rel_parts[-1] == "__init__":
        # An ``__init__.py`` is the package itself.
        package_parts = list(rel_parts[:-1])
        source_module = ".".join(rel_parts[:-1])
    else:
        package_parts = list(rel_parts[:-1])
        source_module = ".".join(rel_parts)
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "janito" or alias.name.startswith("janito."):
                    found.append((node.lineno, source_module, alias.name))
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_target(list(package_parts), node.level, node.module)
            if target and (target == "janito" or target.startswith("janito.")):
                found.append((node.lineno, source_module, target))
    return found


def _collect_edges() -> list[tuple[str, str, str]]:
    """Return sorted ``(location, source_domain, target_domain)`` violations."""
    violations: list[tuple[str, str, str]] = []
    for source_file in sorted(PACKAGE_DIR.rglob("*.py")):
        for lineno, source_module, target_module in _imports_of(source_file):
            source_domain = _domain_of(source_module)
            target_domain = _domain_of(target_module)
            if source_domain == target_domain:
                continue
            allowed = ALLOWED_EDGES.get(source_domain, set())
            if target_domain not in allowed:
                rel = source_file.relative_to(REPO_ROOT)
                violations.append((f"{rel}:{lineno}", source_domain, target_domain))
    return violations


def _scanned_files() -> list[Path]:
    """Return the Python files the boundary scan covers."""
    return sorted(PACKAGE_DIR.rglob("*.py"))


def test_import_graph_respects_domain_boundaries():
    """No cross-domain import may fall outside the allowed matrix."""
    assert PACKAGE_DIR.is_dir(), f"Package dir missing: {PACKAGE_DIR}"
    files = _scanned_files()
    assert files, f"Boundary scan covered zero files under {PACKAGE_DIR}"
    violations = _collect_edges()
    assert not violations, (
        "Cross-domain imports violate the allowed dependency matrix (issue #90):\n"
        + "\n".join(f"  {where}: {source} -> {target}" for where, source, target in violations)
        + "\nUpdate the code (or, only after a deliberate boundary decision, "
        "the ALLOWED_EDGES matrix in this test and dev-docs/ARCHITECTURE.md)."
    )


def test_scan_is_nonempty():
    """The guard must actually scan the package (regression for tests/ root bug)."""
    assert PACKAGE_DIR.is_dir(), f"Package dir missing: {PACKAGE_DIR}"
    files = _scanned_files()
    assert len(files) > 50, f"Expected to scan the real package, got {len(files)} files"


def test_synthetic_forbidden_import_is_flagged():
    """A synthetic disallowed edge must be reported as a violation."""
    # llm_adapters may only target providers; root must be flagged.
    assert "root" not in ALLOWED_EDGES["llm_adapters"]
    assert _domain_of("janito.llm_adapters.responses") == "llm_adapters"
    assert _domain_of("janito.runtime_config") == "root"


def test_allowed_matrix_domains_are_known():
    """Every source/target domain in the matrix must be a real domain."""
    for source, targets in ALLOWED_EDGES.items():
        assert source in DOMAINS, f"Unknown source domain {source!r}"
        for target in targets:
            assert target in DOMAINS, f"Unknown target domain {target!r}"


def test_acp_domain_is_explicit():
    """The ACP entry layer is a first-class domain targeting web + root."""
    assert _domain_of("janito.acp.agent") == "acp"
    assert _domain_of("janito.acp.server") == "acp"
    assert ALLOWED_EDGES["acp"] == {"root", "web"}
    assert "acp" in ALLOWED_EDGES["root"]


def test_async_confined_to_web_and_acp():
    """Only the web backend and the ACP entry layer may use ``async def``."""
    offenders = []
    for source_file in sorted(PACKAGE_DIR.rglob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                rel = source_file.relative_to(REPO_ROOT).as_posix()
                if not (rel.startswith("janito/web/") or rel.startswith("janito/acp/")):
                    offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, "async def outside janito/web and janito/acp:\n" + "\n".join(offenders)


if __name__ == "__main__":  # pragma: no cover - manual diagnostics
    sys.path.insert(0, str(REPO_ROOT))
    violations = _collect_edges()
    if violations:
        for where, source, target in violations:
            print(f"{where}: {source} -> {target}")
        raise SystemExit(1)
    print("No import-graph violations.")
