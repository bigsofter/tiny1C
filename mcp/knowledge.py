# -*- coding: utf-8 -*-
"""Знания сетевого сервиса: текущий снимок и его горячая подгрузка из git.

Сервис (mcp/httpd.py) стартует со встроенной копией набора — деревом, которое
лежит рядом с кодом (в образе это дерево на момент сборки). Дальше раз в
несколько минут он спрашивает у git ревизию ветки `main` набора и, если она
сдвинулась, забирает дерево ревизии, проверяет его и подменяет снимок целиком.

Что здесь принципиально:

  * из git берутся ТОЛЬКО данные: дерево распаковывается в каталог данных и
    читается как тексты; `sys.path` его не видит, ни один файл оттуда не
    исполняется. Код сервиса меняется только новым образом;
  * проверяет дерево код образа — scripts/manifest.py, который приехал с
    сервисом, через collect(root=дерево). Манифест ревизии тоже пересобирается
    этим кодом: сервер верит только тому манифесту, который понимает сам;
  * замена атомарна: новое дерево лежит в своём каталоге trees/<sha>, снимок в
    памяти подменяется одним присваиванием, символьная ссылка `current`
    переписывается через os.replace. Запрос, начавшийся на старом снимке, на
    нём и закончится;
  * битая ревизия (ошибки манифеста, не распаковалась, не прочиталась) не
    подключается: остаёмся на прошлой исправной, ошибка видна в /healthz, повтор
    — только когда main сдвинется дальше. Два последних дерева хранятся — это и
    есть откат, если понадобится вернуться руками.

Каталог данных:
  <data>/repo/            голый репозиторий (fetch только нужной ветки, shallow)
  <data>/trees/<sha>/     распакованные ревизии (хранятся последние две)
  <data>/current -> trees/<sha>   что загружено сейчас (при старте читается первым)
"""

import datetime
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tarfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import snapshot as snap  # noqa: E402

ROOT = snap.ROOT
DEFAULT_REPO = "https://github.com/bigsofter/tiny1C"
DEFAULT_BRANCH = "main"
GIT_TIMEOUT = 120      # секунд на одну git-операцию
KEEP_TREES = 2         # текущее + одно предыдущее дерево для отката

_builder = None


def builder():
    """scripts/manifest.py образа как модуль (scripts — не пакет, грузится по пути)."""
    global _builder
    if _builder is None:
        path = os.path.join(ROOT, "scripts", "manifest.py")
        spec = importlib.util.spec_from_file_location("tiny1c_manifest_builder", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _builder = module
    return _builder


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


class SyncError(Exception):
    pass


def git(args, cwd, timeout=GIT_TIMEOUT):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", LC_ALL="C")
    try:
        done = subprocess.run(["git"] + list(args), cwd=cwd, env=env, timeout=timeout,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SyncError("git %s: %s" % (" ".join(args[:2]), error))
    if done.returncode != 0:
        raise SyncError("git %s: %s" % (" ".join(args[:2]),
                                        done.stderr.decode("utf-8", "replace").strip()[-500:]))
    return done.stdout


def validate_tree(tree):
    """Проверка дерева кодом образа; возвращает текст пересобранного manifest.json."""
    build = builder()
    manifest, errors = build.collect(root=tree)
    if errors:
        shown = errors[:5]
        raise SyncError("манифест: %d ошибок: %s" % (len(errors), "; ".join(shown)))
    if not manifest["направления"]:
        raise SyncError("в дереве нет ни одного направления")
    return build.render(manifest)


class Knowledge:
    """Текущий снимок знаний и синхронизация с git."""

    def __init__(self, image_root=None, data_dir=None, repo_url=DEFAULT_REPO,
                 branch=DEFAULT_BRANCH, log=None):
        self.image_root = ROOT if image_root is None else os.path.abspath(image_root)
        self.data_dir = None if data_dir is None else os.path.abspath(data_dir)
        self.repo_url = repo_url
        self.branch = branch
        self.log = log or (lambda message: sys.stderr.write(message + "\n"))
        self.lock = threading.Lock()
        self.current = None
        self.source = "образ"
        self.last_sync = {"время": None, "ок": None, "ревизия": None, "ошибка": None}
        self.bad_revision = None

    # --- старт -------------------------------------------------------------

    def start(self):
        """Снимок при старте: последнее исправное дерево из каталога данных, иначе встроенная копия."""
        if self.data_dir:
            for name in ("trees", "repo"):
                os.makedirs(os.path.join(self.data_dir, name), exist_ok=True)
            current = os.path.join(self.data_dir, "current")
            if os.path.islink(current) and os.path.isdir(current):
                sha = os.path.basename(os.path.realpath(current))
                try:
                    self.current = snap.load(os.path.realpath(current), revision=sha)
                    self.current.loaded_at = now()
                    self.source = "git"
                    self.log("tiny1c: знания из каталога данных, ревизия %s" % sha)
                    return self.current
                except (OSError, ValueError) as error:
                    self.log("tiny1c: дерево %s не читается (%s), беру встроенную копию" % (sha, error))
        self.current = snap.load(self.image_root)
        self.current.loaded_at = now()
        self.source = "образ"
        self.log("tiny1c: знания — встроенная копия (%s)" % self.current.digest)
        return self.current

    # --- синхронизация -----------------------------------------------------

    def remote_revision(self):
        out = git(["ls-remote", "--heads", self.repo_url, "refs/heads/" + self.branch],
                  cwd=self.data_dir)
        line = out.decode("utf-8", "replace").strip().split("\n")[0]
        sha = line.split("\t", 1)[0].strip() if line else ""
        if len(sha) != 40:
            raise SyncError("ветка %s в %s не найдена" % (self.branch, self.repo_url))
        return sha

    def fetch_tree(self, sha):
        """Дерево ревизии в trees/<sha> (распаковка tar из git archive, без исполнения чего-либо)."""
        repo = os.path.join(self.data_dir, "repo")
        if not os.path.exists(os.path.join(repo, "HEAD")):
            git(["init", "-q", "--bare", repo], cwd=self.data_dir)
        git(["fetch", "-q", "--depth", "1", self.repo_url, "+refs/heads/%s:refs/remotes/origin/%s"
             % (self.branch, self.branch)], cwd=repo)
        have = git(["rev-parse", "refs/remotes/origin/" + self.branch], cwd=repo)
        have = have.decode("ascii", "replace").strip()
        if have != sha:
            raise SyncError("ветка сдвинулась во время загрузки (%s != %s)" % (have[:12], sha[:12]))
        archive = git(["archive", "--format=tar", sha], cwd=repo)
        target = os.path.join(self.data_dir, "trees", sha)
        staging = target + ".tmp"
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging)
        try:
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                try:
                    tar.extractall(staging, filter="data")  # Python 3.12+/3.11.4+: без выхода за каталог
                except TypeError:
                    tar.extractall(staging)
        except (tarfile.TarError, OSError) as error:
            shutil.rmtree(staging, ignore_errors=True)
            raise SyncError("распаковка %s: %s" % (sha[:12], error))
        shutil.rmtree(target, ignore_errors=True)
        os.replace(staging, target)
        return target

    def activate(self, tree, sha, manifest_text):
        """Подменить снимок: манифест ревизии — пересобранный кодом образа."""
        with open(os.path.join(tree, "manifest.json"), "w", encoding="utf-8") as handle:
            handle.write(manifest_text)
        loaded = snap.load(tree, revision=sha, manifest_text=manifest_text)
        loaded.loaded_at = now()
        link = os.path.join(self.data_dir, "current")
        tmp = link + ".tmp"
        if os.path.lexists(tmp):
            os.remove(tmp)
        os.symlink(os.path.join("trees", sha), tmp)
        os.replace(tmp, link)
        with self.lock:
            self.current = loaded
            self.source = "git"
        self.prune(keep=sha)
        return loaded

    def prune(self, keep):
        trees = os.path.join(self.data_dir, "trees")
        names = [name for name in os.listdir(trees) if os.path.isdir(os.path.join(trees, name))]
        names.sort(key=lambda name: os.path.getmtime(os.path.join(trees, name)), reverse=True)
        kept = [keep] + [name for name in names if name != keep]
        for name in kept[KEEP_TREES:]:
            shutil.rmtree(os.path.join(trees, name), ignore_errors=True)

    def sync_once(self):
        """Один цикл: ревизия ветки -> новое? -> дерево -> проверка -> замена. True, если снимок сменился."""
        if not self.data_dir:
            return False
        sha = None
        try:
            sha = self.remote_revision()
            if self.current is not None and sha == self.current.revision:
                self.last_sync = {"время": now(), "ок": True, "ревизия": sha, "ошибка": None}
                return False
            if sha == self.bad_revision:
                self.last_sync = dict(self.last_sync, **{"время": now()})
                return False
            tree = self.fetch_tree(sha)
            manifest_text = validate_tree(tree)
            committed = os.path.join(tree, "manifest.json")
            if os.path.exists(committed):
                with open(committed, encoding="utf-8") as handle:
                    if handle.read().replace("\r\n", "\n") != manifest_text:
                        self.log("tiny1c: manifest.json ревизии %s отличается от пересобранного — "
                                 "беру свой" % sha[:12])
            self.activate(tree, sha, manifest_text)
            self.last_sync = {"время": now(), "ок": True, "ревизия": sha, "ошибка": None}
            self.bad_revision = None
            self.log("tiny1c: знания обновлены до %s (%s)" % (sha[:12], self.current.digest))
            return True
        except SyncError as error:
            if sha:
                self.bad_revision = sha
                shutil.rmtree(os.path.join(self.data_dir, "trees", sha), ignore_errors=True)
            self.last_sync = {"время": now(), "ок": False, "ревизия": sha, "ошибка": str(error)}
            self.log("tiny1c: синхронизация не удалась: %s" % error)
            return False

    def run(self, interval, stop):
        """Фоновый цикл: sync_once каждые `interval` секунд, пока не взведён stop (threading.Event)."""
        while not stop.is_set():
            self.sync_once()
            stop.wait(interval)

    # --- состояние для /healthz -------------------------------------------

    def status(self):
        with self.lock:
            current = self.current
        return {
            "ревизия": None if current is None else current.revision,
            "версия": None if current is None else current.digest,
            "источник": self.source,
            "загружено": None if current is None else current.loaded_at,
            "направлений": None if current is None else current.get("направлений"),
            "инструкций": None if current is None else current.get("инструкций"),
            "последняя_синхронизация": dict(self.last_sync),
            "репозиторий": self.repo_url if self.data_dir else None,
            "ветка": self.branch if self.data_dir else None,
        }
