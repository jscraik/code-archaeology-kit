from code_archaeology.utils import classify_path


def test_classify_path_marks_root_tests_directory_as_test():
    assert classify_path("tests/helpers/util.py") == "test"
    assert classify_path("test/helpers/util.py") == "test"


def test_classify_path_does_not_treat_latest_as_test():
    assert classify_path("src/latest_util.py") == "product"


def test_classify_path_does_not_treat_product_words_as_infra():
    assert classify_path("src/dockerize.py") == "product"
    assert classify_path("src/terraforming.py") == "product"
    assert classify_path("src/k8s_helper.py") == "product"
    assert classify_path("src/docker/client.py") == "product"
    assert classify_path("src/ops/tasks.py") == "product"


def test_classify_path_prefers_docs_directory_over_yaml_extension():
    assert classify_path("docs/architecture.yaml") == "docs"
    assert classify_path("src/config.yaml") == "product"


def test_classify_path_keeps_github_markdown_as_infra():
    assert classify_path(".github/README.md") == "infra"


def test_classify_path_keeps_top_level_infra_directories_as_infra():
    assert classify_path("docker/compose.yml") == "infra"
    assert classify_path("ops/deploy.sh") == "infra"
    assert classify_path("scripts/terraform/plan.sh") == "infra"


def test_classify_path_does_not_treat_substring_build_dist_names_as_generated():
    assert classify_path("src/mydist/component.py") == "product"
    assert classify_path("src/rebuild/task.py") == "product"


def test_classify_path_keeps_real_generated_directories_generated():
    assert classify_path("dist/app.js") == "generated"
    assert classify_path("packages/web/dist/app.js") == "generated"
    assert classify_path("src/dist/app.js") == "generated"
    assert classify_path("src/build/output.py") == "generated"


def test_classify_path_marks_virtualenv_and_coverage_paths_generated():
    assert classify_path(".venv/lib/python/site.py") == "generated"
    assert classify_path("venv/lib/python/site.py") == "generated"
    assert classify_path("coverage/index.html") == "generated"


def test_classify_path_marks_lockfiles_generated():
    assert classify_path("poetry.lock") == "generated"
    assert classify_path("src/package-lock.lock") == "generated"
