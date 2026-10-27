# -*- coding: utf-8 -*-
"""Горячая подгрузка знаний из git (mcp/knowledge.py): новая ревизия подключается, битая — нет.

Репозиторий — локальный каталог с фикстурой (git сам по себе; сеть не нужна).
"""

import json
import os
import shutil
import tempfile
import unittest

from tests import knowledge_fixture as kf

knowledge = kf.load_module("tiny1c_knowledge", "mcp", "knowledge.py")


@unittest.skipUnless(shutil.which("git"), "нужен git")
class Sync(unittest.TestCase):

    def setUp(self):
        self.tree = kf.fixture_copy(self)
        self.repo, self.sha1 = kf.git_repo(self, self.tree)
        self.data = tempfile.mkdtemp(prefix="tiny1c-data-")
        self.addCleanup(shutil.rmtree, self.data, True)
        self.image = kf.fixture_copy(self, prefix="tiny1c-image-")
        self.messages = []
        self.kn = knowledge.Knowledge(image_root=self.image, data_dir=self.data,
                                      repo_url=self.repo, branch="main", log=self.messages.append)
        self.kn.start()

    def tool(self, track="ut"):
        instructions = kf.load_module("tiny1c_instructions_sync", "mcp", "instructions.py")
        return instructions.tool_get_instructions(self.kn.current, {"track": track})

    def test_starts_embedded_then_takes_main(self):
        self.assertEqual("встроенная", self.kn.current.revision)
        self.assertTrue(self.kn.sync_once())
        self.assertEqual(self.sha1, self.kn.current.revision)
        self.assertEqual("git", self.kn.source)
        self.assertEqual(self.sha1, self.tool()["ревизия"])
        link = os.path.join(self.data, "current")
        self.assertTrue(os.path.islink(link))
        self.assertEqual(self.sha1, os.path.basename(os.path.realpath(link)))
        self.assertTrue(os.path.isfile(os.path.join(link, "manifest.json")))
        status = self.kn.status()
        self.assertTrue(status["последняя_синхронизация"]["ок"])
        self.assertEqual(self.sha1, status["ревизия"])
        # та же ревизия — ничего не делает
        self.assertFalse(self.kn.sync_once())

    def test_new_commit_is_picked_up_and_old_tree_kept_for_rollback(self):
        self.kn.sync_once()
        with open(os.path.join(self.tree, "tracks", "ut", "where_is.md"), "a", encoding="utf-8") as handle:
            handle.write("| Появилось после второго коммита | Продажи | Продажи → Новое |\n")
        sha2 = kf.commit_all(self.tree, "правка заметок")
        self.assertTrue(self.kn.sync_once())
        self.assertEqual(sha2, self.kn.current.revision)
        self.assertIn("после второго коммита", self.tool()["текст"])
        trees = sorted(os.listdir(os.path.join(self.data, "trees")))
        self.assertEqual(sorted([self.sha1, sha2]), trees)
        # третья ревизия вытесняет первую: хранятся две
        with open(os.path.join(self.tree, "tracks", "ut", "faq.md"), "a", encoding="utf-8") as handle:
            handle.write("- Ещё вопрос.\n")
        sha3 = kf.commit_all(self.tree, "ещё вопрос")
        self.assertTrue(self.kn.sync_once())
        self.assertEqual(sorted([sha2, sha3]), sorted(os.listdir(os.path.join(self.data, "trees"))))

    def test_broken_revision_is_rejected_and_not_retried(self):
        self.kn.sync_once()
        profile = os.path.join(self.tree, "tracks", "ka", "profile.json")
        with open(profile, "w", encoding="utf-8") as handle:
            handle.write('{"семейство": "ka", "имена": ["КомплекснаяАвтоматизация"], '
                         '"тема": "x", "расширяет": "нет-такого"}\n')
        bad = kf.commit_all(self.tree, "битый профиль")
        self.assertFalse(self.kn.sync_once())
        self.assertEqual(self.sha1, self.kn.current.revision)
        status = self.kn.status()["последняя_синхронизация"]
        self.assertFalse(status["ок"])
        self.assertEqual(bad, status["ревизия"])
        self.assertIn("расширяет", status["ошибка"])
        self.assertEqual(self.sha1, os.path.basename(os.path.realpath(os.path.join(self.data, "current"))))
        self.assertNotIn(bad, os.listdir(os.path.join(self.data, "trees")))
        # повтор на той же битой ревизии не тянет дерево заново
        fetched = len([m for m in self.messages if "не удалась" in m])
        self.assertFalse(self.kn.sync_once())
        self.assertEqual(fetched, len([m for m in self.messages if "не удалась" in m]))
        # починили — подключилось
        with open(profile, "w", encoding="utf-8") as handle:
            json.dump({"семейство": "ka", "имена": ["КомплекснаяАвтоматизация"], "тема": "x",
                       "расширяет": "ut"}, handle, ensure_ascii=False)
        fixed = kf.commit_all(self.tree, "починен профиль")
        self.assertTrue(self.kn.sync_once())
        self.assertEqual(fixed, self.kn.current.revision)
        self.assertTrue(self.kn.status()["последняя_синхронизация"]["ок"])

    def test_invalid_json_and_not_utf8_are_rejected(self):
        self.kn.sync_once()
        chips = os.path.join(self.tree, "tracks", "ut", "chips.json")
        with open(chips, "w", encoding="utf-8") as handle:
            handle.write("[{не json}\n")
        kf.commit_all(self.tree, "битые чипы")
        self.assertFalse(self.kn.sync_once())
        self.assertIn("chips.json", self.kn.status()["последняя_синхронизация"]["ошибка"])
        with open(chips, "wb") as handle:
            handle.write(b"[]\n")
        with open(os.path.join(self.tree, "tracks", "ut", "faq.md"), "wb") as handle:
            handle.write("- кракозябры\n".encode("cp1251"))
        kf.commit_all(self.tree, "cp1251")
        self.assertFalse(self.kn.sync_once())
        self.assertIn("UTF-8", self.kn.status()["последняя_синхронизация"]["ошибка"])
        self.assertEqual(self.sha1, self.kn.current.revision)

    def test_restart_reads_current_tree_before_embedded(self):
        self.kn.sync_once()
        again = knowledge.Knowledge(image_root=self.image, data_dir=self.data, repo_url=self.repo,
                                    log=self.messages.append)
        again.start()
        self.assertEqual(self.sha1, again.current.revision)
        self.assertEqual("git", again.source)

    def test_unreachable_repo_keeps_embedded(self):
        broken = knowledge.Knowledge(image_root=self.image, data_dir=self.data,
                                     repo_url=os.path.join(self.data, "нет-такого-репо"),
                                     log=self.messages.append)
        broken.start()
        self.assertFalse(broken.sync_once())
        self.assertEqual("встроенная", broken.current.revision)
        self.assertFalse(broken.status()["последняя_синхронизация"]["ок"])

    def test_no_data_dir_means_no_sync(self):
        plain = knowledge.Knowledge(image_root=self.image, log=self.messages.append)
        plain.start()
        self.assertFalse(plain.sync_once())
        self.assertIsNone(plain.status()["репозиторий"])

    def test_tree_code_is_never_imported(self):
        # Даже если в ревизии появится «mcp/server.py», сервис его не исполняет: дерево — только данные.
        os.makedirs(os.path.join(self.tree, "mcp"), exist_ok=True)
        with open(os.path.join(self.tree, "mcp", "server.py"), "w", encoding="utf-8") as handle:
            handle.write("raise SystemExit('исполнили код из git')\n")
        with open(os.path.join(self.tree, "scripts_manifest_marker.py"), "w", encoding="utf-8") as handle:
            handle.write("raise SystemExit('исполнили код из git')\n")
        sha = kf.commit_all(self.tree, "код в ревизии")
        self.assertTrue(self.kn.sync_once())
        self.assertEqual(sha, self.kn.current.revision)
        import sys
        self.assertFalse(any(path.startswith(self.data) for path in sys.path))


if __name__ == "__main__":
    unittest.main()
