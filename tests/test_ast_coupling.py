from pathlib import Path
from code_archaeology.ast_coupling import check_logical_coupling

def test_ast_python_coupling(tmp_path: Path):
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)
    
    a_py = src / "a.py"
    b_py = src / "b.py"
    c_py = src / "c.py"
    
    a_py.write_text("import os\nfrom src import b")
    b_py.write_text("import sys")
    c_py.write_text("from src.a import some_func")
    
    # a explicitly imports b
    assert check_logical_coupling(repo, "src/a.py", "src/b.py") is True
    # b doesn't import a, but a imports b, so check_logical_coupling returns true (bidirectional test)
    assert check_logical_coupling(repo, "src/b.py", "src/a.py") is True
    
    # c imports a
    assert check_logical_coupling(repo, "src/c.py", "src/a.py") is True
    
    # b and c are not coupled
    assert check_logical_coupling(repo, "src/b.py", "src/c.py") is False


def test_ast_javascript_coupling(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)
    
    main_js = js_dir / "main.js"
    utils_js = js_dir / "utils.js"
    consts_ts = js_dir / "consts.ts"
    
    main_js.write_text("import { util } from './utils.js';")
    utils_js.write_text("const a = require('../js/consts')")
    consts_ts.write_text("export const VALUE = 1;")
    
    # main imports utils
    assert check_logical_coupling(repo, "js/main.js", "js/utils.js") is True
    # utils imports consts
    assert check_logical_coupling(repo, "js/utils.js", "js/consts.ts") is True
    # main does not import consts
    assert check_logical_coupling(repo, "js/main.js", "js/consts.ts") is False
