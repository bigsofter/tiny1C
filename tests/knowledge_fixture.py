# -*- coding: utf-8 -*-
"""Общее для тестов сетевого режима: копия фикстуры знаний, снимок, git-репозиторий из неё.

Фикстура tests/fixtures/knowledge — синтетический набор: ядро со шпаргалками,
`ut` с полным пакетом инструкций, `ka` с «расширяет: ut», `unf` без пакета.
Имена конфигураций и тексты вымышленные ровно настолько, чтобы проверить разбор.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "knowledge")
MCP = os.path.join(ROOT, "mcp")
if MCP not in sys.path:
    sys.path.insert(0, MCP)


def load_module(name, *parts):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, *parts))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_copy(case, prefix="tiny1c-kn-"):
    """Временная копия фикстуры с пересобранным manifest.json; удаляется после теста."""
    tmp = tempfile.mkdtemp(prefix=prefix)
    cleanup = case.addClassCleanup if isinstance(case, type) else case.addCleanup
    cleanup(shutil.rmtree, tmp, True)
    tree = os.path.join(tmp, "tree")
    shutil.copytree(FIXTURE, tree, ignore=shutil.ignore_patterns("__pycache__"))
    builder = load_module("tiny1c_manifest_fixture", "scripts", "manifest.py")
    manifest, errors = builder.collect(root=tree)
    if errors:
        raise AssertionError(errors)
    with open(os.path.join(tree, "manifest.json"), "w", encoding="utf-8") as handle:
        handle.write(builder.render(manifest))
    return tree


def snapshot_of(tree, revision="встроенная"):
    import snapshot
    return snapshot.load(tree, revision=revision)


def git(args, cwd):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
    done = subprocess.run(["git"] + list(args), cwd=cwd, env=env, check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return done.stdout.decode("utf-8").strip()


def git_repo(case, tree):
    """Репозиторий с одним коммитом дерева фикстуры на ветке main; возвращает (путь, sha)."""
    git(["init", "-q", "-b", "main"], tree)
    git(["add", "-A"], tree)
    git(["commit", "-q", "-m", "фикстура"], tree)
    return tree, git(["rev-parse", "HEAD"], tree)


def commit_all(tree, message):
    git(["add", "-A"], tree)
    git(["commit", "-q", "-m", message], tree)
    return git(["rev-parse", "HEAD"], tree)
