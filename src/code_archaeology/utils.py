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
    "**/node_modules/**",
    "dist/**",
    "**/dist/**",
    "build/**",
    "**/build/**",
    "target/**",
    "**/target/**",
    ".venv/**",
    "**/.venv/**",
    "venv/**",
    "**/venv/**",
    "coverage/**",
    "**/coverage/**",
    "*.lock",
    "**/*.lock",
]

LOW_VALUE_ABANDONED_GLOBS = [
    ".github/**",
    "docs/**",
    "ISSUE_TEMPLATE/**",
    "**/ISSUE_TEMPLATE/**",
    "*.md",
    "**/*.md",
]


class ArchaeologyError(Exception):
    """Raised for CLI contract and runtime failures."""

def _notice(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}

def sanitize(value: str, max_len: int = 400) -> str:
    cleaned = CONTROL_CHARS_RE.sub("", value).replace("\r", " ").replace("\n", " ").strip()
    return cleaned[:max_len] + ("..." if len(cleaned) > max_len else "")

def sanitize_path(value: str, max_len: int | None = None) -> str:
    cleaned = CONTROL_CHARS_RE.sub("", value).replace("\r", " ").replace("\n", " ")
    if max_len is None:
        return cleaned
    return cleaned[:max_len] + ("..." if len(cleaned) > max_len else "")

def normalize_path(path: str) -> str:
    return path.replace("\\", "/")

def matches_any(path: str, patterns: list[str]) -> bool:
    normalized = normalize_path(path)
    return any(fnmatch.fnmatch(normalized, pattern) for pattern in patterns)

def classify_path(path: str) -> str:
    p = normalize_path(path).lower()
    name = p.split("/")[-1]
    segments = [segment for segment in p.split("/") if segment]
    top_segment = segments[0] if segments else ""
    infra_segments = {"infra", "ops", "docker", "k8s", "terraform"}
    app_like_roots = {"src", "lib", "app", "test", "tests", "fixtures", "docs"}
    generated_segments = {"dist", "build", "target", "node_modules"}

    if "__pycache__" in p or name.endswith(".pyc"):
        return "generated"
    if (
        p.startswith("test/")
        or p.startswith("tests/")
        or p.startswith("fixtures/")
        or name.startswith("test_")
        or any(token in p for token in ["/test/", "/tests/", "/fixtures/", "/__tests__/"])
    ):
        return "test"
    if p.startswith("docs/"):
        return "docs"
    if (
        p.startswith(".github/")
        or top_segment in {"infra", "ops", "docker", "k8s", "terraform"}
        or (
            any(segment in infra_segments for segment in segments)
            and top_segment not in app_like_roots
        )
        or (
            name.endswith((".yml", ".yaml"))
            and top_segment not in app_like_roots
        )
    ):
        return "infra"
    if name.endswith(".md"):
        return "docs"
    if top_segment in generated_segments or any(segment in generated_segments for segment in segments):
        return "generated"
    if top_segment in {"src", "lib", "app"} or any(segment in {"src", "lib", "app"} for segment in segments):
        return "product"
    return "unknown"

def confidence(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"
