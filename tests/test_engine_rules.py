"""Hard rules from CLAUDE.md, enforced by tests rather than by memory."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine"

AI_AND_NETWORK_MODULES = {"openai", "azure", "agent_framework", "anthropic", "httpx", "requests", "aiohttp"}
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", "dist", "Claude MD file", "Perplexity MD file"}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".html", ".css", ".ts", ".tsx", ".json", ".txt", ".yml", ".yaml", ".bicep"}
EM_DASH = chr(0x2014)


def engine_files() -> list[Path]:
    return sorted(ENGINE.rglob("*.py"))


def imported_modules(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_engine_never_calls_a_model_or_the_network():
    for path in engine_files():
        bad = imported_modules(ast.parse(path.read_text(encoding="utf-8"))) & AI_AND_NETWORK_MODULES
        assert not bad, f"{path.name} imports {sorted(bad)}; engine/ must stay deterministic"


def test_all_randomness_goes_through_rng_module():
    for path in engine_files():
        if path.name == "rng.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert "random" not in imported_modules(tree), f"{path.name} imports random; use engine.rng"
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "random" and isinstance(node.value, ast.Name):
                assert node.value.id not in {"np", "numpy"}, f"{path.name} uses np.random; use engine.rng"


def test_no_em_dashes_anywhere():
    offenders = []
    for path in ROOT.rglob("*"):
        if path.suffix not in TEXT_SUFFIXES or any(part in SKIP_DIRS for part in path.parts):
            continue
        if EM_DASH in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"em dashes found in {offenders}"
