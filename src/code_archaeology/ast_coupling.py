import ast
import re
from pathlib import Path

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
            if node.module:
                imports.add(node.module)
    return imports

JS_IMPORT_RE = re.compile(r"""(?:import\s+.*?\s+from\s+|import\s+)['"]([^'"]+)['"]|require\(['"]([^'"]+)['"]\)""")

def extract_js_imports(file_path: Path) -> set[str]:
    if not file_path.exists():
        return set()
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return set()
    
    imports = set()
    for match in JS_IMPORT_RE.finditer(content):
        # Match group 1 is import/from, group 2 is require
        imp = match.group(1) or match.group(2)
        if imp:
            # remove leading ./ or ../ or trailing .js
            imp = re.sub(r'^\./|^\.\./', '', imp)
            imp = re.sub(r'\.(js|ts|jsx|tsx)$', '', imp)
            imports.add(imp)
    return imports

def check_logical_coupling(repo_root: Path, file_a: str, file_b: str) -> bool:
    """Check if file_a imports file_b or vice versa."""
    path_a = repo_root / file_a
    path_b = repo_root / file_b
    
    ext_a = path_a.suffix.lower()
    ext_b = path_b.suffix.lower()
    
    imports_a = set()
    if ext_a == '.py':
        imports_a = extract_python_imports(path_a)
    elif ext_a in {'.js', '.ts', '.jsx', '.tsx'}:
        imports_a = extract_js_imports(path_a)
        
    imports_b = set()
    if ext_b == '.py':
        imports_b = extract_python_imports(path_b)
    elif ext_b in {'.js', '.ts', '.jsx', '.tsx'}:
        imports_b = extract_js_imports(path_b)
        
    # Simplify file paths to module names
    def to_mod(p: str, ext: str) -> str:
        s = p
        if ext == '.py':
            s = s.replace('.py', '').replace('/', '.')
            if s.endswith('.__init__'):
                s = s[:-9]
        else:
            s = s.replace(ext, '').split('/')[-1]
        return s
        
    mod_a = to_mod(file_a, ext_a)
    mod_b = to_mod(file_b, ext_b)
    
    # Check if a imports b
    for imp in imports_a:
        if mod_b in imp or imp in mod_b:  # lenient matching
            return True
            
    # Check if b imports a
    for imp in imports_b:
        if mod_a in imp or imp in mod_a:
            return True
            
    return False
