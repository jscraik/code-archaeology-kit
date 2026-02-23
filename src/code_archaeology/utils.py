from __future__ import annotations
import fnmatch
import re

CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

DEFAULT_IGNORE_GLOBS = [
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
    "node_modules/**",
    "dist/**",
    "build/**",
    "target/**",
    ".venv/**",
    "venv/**",
    "coverage/**",
    "*.lock",
]

LOW_VALUE_ABANDONED_GLOBS = [
    ".github/**",
    "docs/**",
    "**/ISSUE_TEMPLATE/**",
    "**/*.md",
]


class ArchaeologyError(Exception):
    """Raised for CLI contract and runtime failures."""

def _notice(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}

def sanitize(value: str, max_len: int = 400) -> str:
    cleaned = CONTROL_CHARS_RE.sub("", value).replace("\r", " ").replace("\n", " ").strip()
    return cleaned[:max_len] + ("..." if len(cleaned) > max_len else "")

def normalize_path(path: str) -> str:
    return path.replace("\\", "/")

def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = normalize_path(path)
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)

def classify_path(path: str) -> str:
    p = normalize_path(path).lower()
    name = p.split("/")[-1]

    if "__pycache__" in p or name.endswith(".pyc"):
        return "generated"
    if any(token in p for token in ["/test/", "/tests/", "test_", "/fixtures/", "/__tests__/"]):
        return "test"
    if p.startswith(".github/") or any(token in p for token in ["/infra/", "/ops/", "docker", "k8s", "terraform", ".yml", ".yaml"]):
        return "infra"
    if p.startswith("docs/") or name.endswith(".md"):
        return "docs"
    if any(token in p for token in ["dist/", "build/", "target/", "node_modules/"]):
        return "generated"
    if any(token in p for token in ["src/", "lib/", "app/"]):
        return "product"
    return "unknown"

def confidence(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"
