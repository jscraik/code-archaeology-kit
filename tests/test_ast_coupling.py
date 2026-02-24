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


def test_ast_python_relative_import_coupling(tmp_path: Path):
    repo = tmp_path / "repo"
    pkg = repo / "pkg"
    pkg.mkdir(parents=True)

    a_py = pkg / "a.py"
    b_py = pkg / "b.py"

    a_py.write_text("from . import b\n")
    b_py.write_text("VALUE = 1\n")

    assert check_logical_coupling(repo, "pkg/a.py", "pkg/b.py") is True


def test_ast_python_src_layout_absolute_import_without_src_prefix(tmp_path: Path):
    repo = tmp_path / "repo"
    pkg = repo / "src" / "pkg"
    pkg.mkdir(parents=True)

    (pkg / "a.py").write_text("from pkg import b\n")
    (pkg / "b.py").write_text("VALUE = 1\n")

    assert check_logical_coupling(repo, "src/pkg/a.py", "src/pkg/b.py") is True


def test_ast_python_stdlib_import_does_not_match_local_same_basename(tmp_path: Path):
    repo = tmp_path / "repo"
    src = repo / "src"
    src.mkdir(parents=True)

    (src / "a.py").write_text("import os\n")
    (src / "os.py").write_text("VALUE = 1\n")

    assert check_logical_coupling(repo, "src/a.py", "src/os.py") is False


def test_ast_python_stdlib_submodule_import_does_not_match_local_module(tmp_path: Path):
    repo = tmp_path / "repo"
    src_http = repo / "src" / "http"
    src_http.mkdir(parents=True)

    (repo / "src" / "a.py").write_text("import http.client\n")
    (src_http / "client.py").write_text("VALUE = 1\n")

    assert check_logical_coupling(repo, "src/a.py", "src/http/client.py") is False


def test_ast_python_stdlib_import_does_not_match_root_same_basename(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)

    (repo / "a.py").write_text("import os\n")
    (repo / "os.py").write_text("VALUE = 1\n")

    assert check_logical_coupling(repo, "a.py", "os.py") is False


def test_ast_python_stdlib_submodule_import_does_not_match_root_package(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "http").mkdir(parents=True)

    (repo / "a.py").write_text("import http.client\n")
    (repo / "http" / "client.py").write_text("VALUE = 1\n")

    assert check_logical_coupling(repo, "a.py", "http/client.py") is False


def test_ast_python_explicit_local_package_shadowing_stdlib_submodule_is_detected(tmp_path: Path):
    repo = tmp_path / "repo"
    src_json = repo / "src" / "json"
    src_json.mkdir(parents=True)
    (src_json / "__init__.py").write_text("")

    (repo / "src" / "a.py").write_text("import json.tool\n")
    (src_json / "tool.py").write_text("VALUE = 1\n")

    assert check_logical_coupling(repo, "src/a.py", "src/json/tool.py") is True


def test_ast_python_parent_relative_import_targets_correct_package_level(tmp_path: Path):
    repo = tmp_path / "repo"
    pkg_sub = repo / "pkg" / "sub"
    pkg_sub.mkdir(parents=True)

    (pkg_sub / "a.py").write_text("from .. import b\n")
    (repo / "pkg" / "b.py").write_text("VALUE = 1\n")
    (pkg_sub / "b.py").write_text("VALUE = 2\n")

    assert check_logical_coupling(repo, "pkg/sub/a.py", "pkg/b.py") is True
    assert check_logical_coupling(repo, "pkg/sub/a.py", "pkg/sub/b.py") is False


def test_ast_python_invalid_parent_relative_import_does_not_create_false_coupling(tmp_path: Path):
    repo = tmp_path / "repo"
    pkg = repo / "pkg"
    pkg.mkdir(parents=True)

    (pkg / "a.py").write_text("from .. import b\n")
    (repo / "b.py").write_text("VALUE = 1\n")

    assert check_logical_coupling(repo, "pkg/a.py", "b.py") is False


def test_ast_python_module_paths_with_dot_py_in_directory_are_handled(tmp_path: Path):
    repo = tmp_path / "repo"
    pkg = repo / "pkg.pytools"
    pkg.mkdir(parents=True)

    (pkg / "a.py").write_text("from pkg.pytools import b\n")
    (pkg / "b.py").write_text("VALUE = 1\n")

    assert check_logical_coupling(repo, "pkg.pytools/a.py", "pkg.pytools/b.py") is True


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


def test_ast_javascript_package_import_not_coupled_to_local_same_name(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("import lodash from 'lodash';")
    (js_dir / "lodash.js").write_text("export const local = true;")

    assert check_logical_coupling(repo, "js/main.js", "js/lodash.js") is False


def test_ast_javascript_relative_path_does_not_match_other_index_file(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    foo_dir = js_dir / "foo"
    bar_dir = js_dir / "bar"
    foo_dir.mkdir(parents=True)
    bar_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("import thing from './foo/index.js';")
    (foo_dir / "index.js").write_text("export default 1;")
    (bar_dir / "index.js").write_text("export default 2;")

    assert check_logical_coupling(repo, "js/main.js", "js/foo/index.js") is True
    assert check_logical_coupling(repo, "js/main.js", "js/bar/index.js") is False


def test_ast_javascript_directory_import_matches_index_file(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    foo_dir = js_dir / "foo"
    foo_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("import thing from './foo';")
    (foo_dir / "index.js").write_text("export default 1;")

    assert check_logical_coupling(repo, "js/main.js", "js/foo/index.js") is True


def test_ast_javascript_dynamic_import_is_detected(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("async function load(){ return import('./feature.js'); }\n")
    (js_dir / "feature.js").write_text("export const FEATURE = true;\n")

    assert check_logical_coupling(repo, "js/main.js", "js/feature.js") is True


def test_ast_javascript_multiline_import_from_is_detected(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("import {\n  feature\n} from './feature.js';\n")
    (js_dir / "feature.js").write_text("export const feature = true;\n")

    assert check_logical_coupling(repo, "js/main.js", "js/feature.js") is True


def test_ast_javascript_dynamic_import_template_literal_is_detected(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("async function load(){ return import(`./feature.js`); }\n")
    (js_dir / "feature.js").write_text("export const feature = true;\n")

    assert check_logical_coupling(repo, "js/main.js", "js/feature.js") is True


def test_ast_javascript_import_with_query_suffix_is_detected(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("import data from './feature.js?raw';\n")
    (js_dir / "feature.js").write_text("export const feature = true;\n")

    assert check_logical_coupling(repo, "js/main.js", "js/feature.js") is True


def test_ast_javascript_dynamic_import_with_magic_comment_is_detected(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("const feature = import(/* webpackChunkName: 'feature' */ './feature.js');\n")
    (js_dir / "feature.js").write_text("export const feature = true;\n")

    assert check_logical_coupling(repo, "js/main.js", "js/feature.js") is True


def test_ast_javascript_require_with_whitespace_is_detected(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("const feature = require ( './feature.js' );\n")
    (js_dir / "feature.js").write_text("module.exports = 1;\n")

    assert check_logical_coupling(repo, "js/main.js", "js/feature.js") is True


def test_ast_javascript_export_from_is_detected(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)

    (js_dir / "index.js").write_text("export { feature } from './feature.js';\n")
    (js_dir / "feature.js").write_text("export const feature = true;\n")

    assert check_logical_coupling(repo, "js/index.js", "js/feature.js") is True


def test_ast_javascript_paths_with_dot_js_in_directory_are_handled(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "app.jslib"
    js_dir.mkdir(parents=True)

    (js_dir / "main.js").write_text("import helper from './helper.js';\n")
    (js_dir / "helper.js").write_text("export default 1;\n")

    assert check_logical_coupling(repo, "app.jslib/main.js", "app.jslib/helper.js") is True


def test_ast_modern_js_extensions_mjs_are_detected(tmp_path: Path):
    repo = tmp_path / "repo"
    js_dir = repo / "js"
    js_dir.mkdir(parents=True)

    (js_dir / "main.mjs").write_text("import helper from './helper.mjs';\n")
    (js_dir / "helper.mjs").write_text("export default 1;\n")

    assert check_logical_coupling(repo, "js/main.mjs", "js/helper.mjs") is True
