import ast
import posixpath
import re
import sys
from pathlib import PurePosixPath
from pathlib import Path

STDLIB_MODULES = set(getattr(sys, "stdlib_module_names", set()))


def extract_python_imports(file_path: Path) -> set[str]:
    """Returns a set of imported module names or file paths."""
    if not file_path.exists():
        return set()
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except Exception:
        return set()
    
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level if node.level else ""
            if node.module:
                imports.add(f"{prefix}{node.module}")
            for alias in node.names:
                if node.module:
                    imports.add(f"{prefix}{node.module}.{alias.name}")
                elif prefix:
                    imports.add(f"{prefix}{alias.name}")
    return imports


JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+|export\s+.*?\s+from\s+|import\s+)[`'"]([^`'"]+)[`'"]|require\s*\(\s*[`'"]([^`'"]+)[`'"]\s*\)|import\s*\(\s*(?:/\*.*?\*/\s*)*[`'"]([^`'"]+)[`'"](?:\s*,[^)]*)?\s*\)""",
    re.DOTALL,
)


def _js_comment_spans(content: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    idx = 0
    length = len(content)
    state: str = "code"

    while idx < length:
        ch = content[idx]
        nxt = content[idx + 1] if idx + 1 < length else ""

        if state == "code":
            if ch == "/" and nxt == "/":
                start = idx
                idx += 2
                while idx < length and content[idx] != "\n":
                    idx += 1
                spans.append((start, idx))
                continue
            if ch == "/" and nxt == "*":
                start = idx
                idx += 2
                while idx + 1 < length and not (content[idx] == "*" and content[idx + 1] == "/"):
                    idx += 1
                idx = min(length, idx + 2)
                spans.append((start, idx))
                continue
            if ch == "'":
                state = "single"
                idx += 1
                continue
            if ch == '"':
                state = "double"
                idx += 1
                continue
            if ch == "`":
                state = "template"
                idx += 1
                continue
            idx += 1
            continue

        if ch == "\\":
            idx += 2
            continue

        if state == "single" and ch == "'":
            state = "code"
        elif state == "double" and ch == '"':
            state = "code"
        elif state == "template" and ch == "`":
            state = "code"
        idx += 1

    return spans


def _in_comment_span(pos: int, spans: list[tuple[int, int]]) -> bool:
    for start, end in spans:
        if start <= pos < end:
            return True
    return False


def extract_js_imports(file_path: Path) -> set[str]:
    if not file_path.exists():
        return set()
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return set()
    
    comment_spans = _js_comment_spans(content)
    imports = set()
    for match in JS_IMPORT_RE.finditer(content):
        if _in_comment_span(match.start(), comment_spans):
            continue
        # Match group 1 is import/from, group 2 is require, group 3 is dynamic import()
        imp = match.group(1) or match.group(2) or match.group(3)
        if not imp:
            continue

        # Consider only local-relative imports to avoid false positives on package names.
        if not imp.startswith(("./", "../", "/")):
            continue

        imp = imp.split("?", 1)[0].split("#", 1)[0]
        imp = re.sub(r"\.(js|ts|jsx|tsx|mjs|cjs|mts|cts)$", "", imp)
        if imp:
            imports.add(imp)
    return imports


def _python_module_candidates(module: str) -> set[str]:
    candidates = {module}
    for prefix in ("src.", "lib.", "app."):
        if module.startswith(prefix):
            trimmed = module[len(prefix):]
            if trimmed:
                candidates.add(trimmed)
    return candidates


def _python_import_matches_module(imp: str, module: str) -> bool:
    candidates = _python_module_candidates(module)
    if imp not in candidates:
        return False
    root = imp.split(".", 1)[0]
    if root in STDLIB_MODULES:
        for candidate in candidates:
            if candidate == root or candidate.startswith(f"{root}."):
                return False
    return True


def _python_import_matches_explicit_stdlib_shadow(
    repo_root: Path,
    module_file: str,
    imp: str,
    module: str,
) -> bool:
    candidates = _python_module_candidates(module)
    if imp not in candidates:
        return False

    imp_parts = tuple(part for part in imp.split(".") if part)
    if len(imp_parts) < 2:
        return False

    root = imp_parts[0]
    if root not in STDLIB_MODULES:
        return False

    file_parts = PurePosixPath(module_file).with_suffix("").parts
    if len(file_parts) < len(imp_parts):
        return False
    start_idx = len(file_parts) - len(imp_parts)
    if tuple(file_parts[start_idx:]) != imp_parts:
        return False

    package_root = Path(repo_root, *file_parts[: start_idx + 1])
    return (package_root / "__init__.py").exists()


def _js_import_matches_module(imp: str, module: str) -> bool:
    return imp == module or module == f"{imp}/index"


def _resolve_js_imports(source_file: str, imports: set[str]) -> set[str]:
    source_dir = PurePosixPath(source_file).parent
    resolved: set[str] = set()

    for imp in imports:
        if imp.startswith("/"):
            normalized = posixpath.normpath(imp.lstrip("/"))
        else:
            normalized = posixpath.normpath(str(source_dir / imp))
        if normalized and normalized != ".":
            resolved.add(normalized)

    return resolved


def _resolve_python_imports(source_file: str, imports: set[str]) -> set[str]:
    source_module = source_file.replace("/", ".").removesuffix(".py")
    if source_module.endswith(".__init__"):
        source_package = source_module[: -len(".__init__")]
    else:
        source_package = source_module.rsplit(".", 1)[0] if "." in source_module else ""
    source_parts = [part for part in source_package.split(".") if part]

    resolved: set[str] = set()
    for imp in imports:
        if not imp.startswith("."):
            resolved.add(imp)
            continue

        level = len(imp) - len(imp.lstrip("."))
        rel_target = imp[level:]
        if level > len(source_parts):
            continue
        if level == 1:
            base_parts = source_parts
        else:
            drop = level - 1
            base_parts = source_parts[:-drop] if drop < len(source_parts) else []

        parts = list(base_parts)
        if rel_target:
            parts.extend(rel_target.split("."))
        if parts:
            resolved.add(".".join(parts))

    return resolved


def _load_resolved_imports(
    repo_root: Path,
    source_file: str,
    ext: str,
    imports_cache: dict[str, set[str]] | None,
) -> set[str]:
    cache_key = f"{ext}:{source_file}"
    if imports_cache is not None and cache_key in imports_cache:
        return imports_cache[cache_key]

    path = repo_root / source_file
    if ext == ".py":
        imports = _resolve_python_imports(source_file, extract_python_imports(path))
    elif ext in {".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}:
        imports = _resolve_js_imports(source_file, extract_js_imports(path))
    else:
        imports = set()

    if imports_cache is not None:
        imports_cache[cache_key] = imports
    return imports


def check_logical_coupling(
    repo_root: Path,
    file_a: str,
    file_b: str,
    imports_cache: dict[str, set[str]] | None = None,
) -> bool:
    """Check if file_a imports file_b or vice versa."""
    ext_a = Path(file_a).suffix.lower()
    ext_b = Path(file_b).suffix.lower()
    
    imports_a = _load_resolved_imports(repo_root, file_a, ext_a, imports_cache)
    imports_b = _load_resolved_imports(repo_root, file_b, ext_b, imports_cache)
        
    # Simplify file paths to module names
    def to_mod(p: str, ext: str) -> str:
        s = p
        if ext == ".py":
            s = s.removesuffix(".py").replace("/", ".")
            if s.endswith(".__init__"):
                s = s[:-9]
        else:
            s = s.removesuffix(ext)
        return s
        
    mod_a = to_mod(file_a, ext_a)
    mod_b = to_mod(file_b, ext_b)

    def matches(imp: str, module: str, module_ext: str, module_file: str) -> bool:
        if module_ext == ".py":
            return _python_import_matches_module(imp, module) or _python_import_matches_explicit_stdlib_shadow(
                repo_root=repo_root,
                module_file=module_file,
                imp=imp,
                module=module,
            )
        return _js_import_matches_module(imp, module)

    # Check if a imports b
    for imp in imports_a:
        if matches(imp, mod_b, ext_b, file_b):
            return True

    # Check if b imports a
    for imp in imports_b:
        if matches(imp, mod_a, ext_a, file_a):
            return True
            
    return False
