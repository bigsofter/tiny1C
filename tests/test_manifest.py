# -*- coding: utf-8 -*-
"""Проверки карточек инструментов в scripts/manifest.py."""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("manifest", os.path.join(ROOT, "scripts", "manifest.py"))
manifest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest)

CARD = """---
id: intro-900
группа: introspection
инструмент: probe
сигнатура: "probe(dump)"
исполнение: offline
опасность: read
идея: "%s"
источник: "решение:тест 2026-09-27, проверка регулярки лицензий"
check: ["fixtures:tests, тест"]
статус: реализован
правила: []
---
"""


class ToolCards(unittest.TestCase):

    def errors_for(self, idea):
        tmp = tempfile.mkdtemp(prefix="tiny1c-")
        saved = manifest.TOOLS_DIR
        try:
            os.makedirs(os.path.join(tmp, "introspection"))
            with open(os.path.join(tmp, "introspection", "probe.md"), "w",
                      encoding="utf-8") as handle:
                handle.write(CARD % idea)
            manifest.TOOLS_DIR = tmp
            errors = []
            manifest.collect_tools(set(), errors)
            return errors
        finally:
            manifest.TOOLS_DIR = saved
            shutil.rmtree(tmp)

    def test_copyleft_by_abbreviation_needs_mark(self):
        self.assertTrue(any("только идея" in item for item in self.errors_for("образец X (AGPL-3.0)")))

    def test_copyleft_spelled_out_needs_mark(self):
        for idea in ("образец X под GNU General Public License v3",
                     "образец X, GNU Affero General Public License",
                     "образец X, GNU Lesser General Public License"):
            self.assertTrue(any("только идея" in item for item in self.errors_for(idea)), idea)

    def test_marked_or_permissive_passes(self):
        self.assertEqual([], self.errors_for("образец X, GNU General Public License — только идея"))
        self.assertEqual([], self.errors_for("образец X (MIT)"))


GUIDE = """---
id: how-901
направление: core
категория: расширения
платформы: [8.3]
заголовок: "Тестовый рецепт"
источник: "практика:тест 2026-10-16, проверка сборки рецептов"
%s
ключи: [слово]
check: ["manual:глазом"]
%s
---

## Шаги
"""


class Guides(unittest.TestCase):
    """collect_guides на временном дереве tracks/core/guides."""

    def collect(self, text, name="how-901.md", seen=None):
        tmp = tempfile.mkdtemp(prefix="tiny1c-guides-")
        try:
            os.makedirs(os.path.join(tmp, "guides"))
            with open(os.path.join(tmp, "guides", name), "w", encoding="utf-8") as handle:
                handle.write(text)
            errors = []
            guides = manifest.collect_guides("core", tmp, set() if seen is None else seen, errors)
            return guides, errors
        finally:
            shutil.rmtree(tmp)

    def good(self, task='задача: "Что получаем"', rules="правила: [ext-002]"):
        return GUIDE % (task, rules)

    def test_good_guide_is_collected(self):
        guides, errors = self.collect(self.good())
        self.assertEqual([], errors)
        self.assertEqual(["how-901"], [guide["id"] for guide in guides])
        self.assertEqual(["ext-002"], guides[0]["правила"])
        self.assertEqual("tracks/core/guides/how-901.md", guides[0]["файл"])
        self.assertEqual(["manual"], guides[0]["виды_проверок"])

    def test_rules_default_is_empty_list(self):
        guides, errors = self.collect(self.good(rules=""))
        self.assertEqual([], errors)
        self.assertEqual([], guides[0]["правила"])

    def test_no_task_is_error(self):
        _, errors = self.collect(self.good(task=""))
        self.assertTrue(any("«задача»" in item for item in errors), errors)

    def test_empty_task_is_error(self):
        _, errors = self.collect(self.good(task='задача: ""'))
        self.assertTrue(any("пустая «задача»" in item for item in errors), errors)

    def test_bad_id_format(self):
        text = self.good().replace("id: how-901", "id: how-9")
        _, errors = self.collect(text, name="how-9.md")
        self.assertTrue(any("не по формату" in item for item in errors), errors)

    def test_id_taken_by_rule(self):
        _, errors = self.collect(self.good(), seen={"how-901"})
        self.assertTrue(any("уже занят" in item for item in errors), errors)

    def test_practice_is_a_source_kind(self):
        self.assertIn("практика", manifest.SOURCES)
        _, errors = self.collect(self.good().replace("практика:", "слух:"))
        self.assertTrue(any("источник" in item for item in errors), errors)

    def test_full_collect_checks_rule_links_and_lists_guides(self):
        tmp = tempfile.mkdtemp(prefix="tiny1c-tree-")
        saved = manifest.TRACKS
        try:
            core = os.path.join(tmp, "core")
            os.makedirs(os.path.join(core, "guides"))
            os.makedirs(os.path.join(core, "rules"))
            with open(os.path.join(core, "track.md"), "w", encoding="utf-8") as handle:
                handle.write('---\nкод: core\nназвание: Ядро\nвид: ядро\n'
                             'платформы: [8.3]\nстатус: ведётся\n---\n')
            with open(os.path.join(core, "guides", "how-901.md"), "w", encoding="utf-8") as handle:
                handle.write(self.good(rules="правила: [ext-777]"))
            manifest.TRACKS = tmp
            built, errors = manifest.collect()
            self.assertTrue(any("ext-777" in item for item in errors), errors)
            self.assertEqual(1, built["рецептов"])
            self.assertEqual(["how-901"], [guide["id"] for guide in built["рецепты"]])
            self.assertEqual(["how-901"], built["направления"][0]["рецепты"])
            self.assertEqual(1, built["направления"][0]["рецептов"])
            self.assertEqual([], built["ловятся_только_человеком"])
        finally:
            manifest.TRACKS = saved
            shutil.rmtree(tmp)


class InstructionPacks(unittest.TestCase):
    """Пакет инструкций по конфигурации: схема profile.json, чипы, «расширяет», потолок размера."""

    GOOD = {"семейство": "bp", "имена": ["БухгалтерияПредприятия"], "тема": "учёт и налоги",
            "синоним_re": "Бухгалтерия предприятия", "мин_версия": "3.0.150",
            "поставщики": ["Фирма \"1С\""], "признаки": {"бухгалтерия": True},
            "план_счетов": "Хозрасчетный", "без_кода": ["Обработка.X"]}

    def tree(self, profile=None, files=None, extra_tracks=()):
        tmp = tempfile.mkdtemp(prefix="tiny1c-pack-")
        self.addCleanup(shutil.rmtree, tmp, True)
        tracks = os.path.join(tmp, "tracks")
        for code, kind in (("bp", "типовая"),) + tuple(extra_tracks):
            os.makedirs(os.path.join(tracks, code))
            with open(os.path.join(tracks, code, "track.md"), "w", encoding="utf-8") as handle:
                handle.write("---\nкод: %s\nназвание: %s\nвид: %s\nплатформы: [8.3]\n"
                             "статус: ведётся\n---\n" % (code, code, kind))
        if profile is not None:
            with open(os.path.join(tracks, "bp", "profile.json"), "w", encoding="utf-8") as handle:
                handle.write(profile if isinstance(profile, str)
                             else json.dumps(profile, ensure_ascii=False))
        for name, text in (files or {}).items():
            with open(os.path.join(tracks, "bp", name), "w", encoding="utf-8") as handle:
                handle.write(text)
        return tmp

    def errors(self, **kw):
        built, errors = manifest.collect(root=self.tree(**kw))
        return built, errors

    def test_good_pack_is_indexed(self):
        built, errors = self.errors(profile=self.GOOD, files={"where_is.md": "| а | б |\n",
                                                            "chips.json": '[{"id": "a", "заголовок": "б", "текст": "в"}]'})
        self.assertEqual([], errors)
        pack = built["направления"][0]["инструкции"]
        self.assertEqual("bp", pack["профиль"]["семейство"])
        self.assertEqual(["where_is.md", "chips.json"], [item["имя"] for item in pack["файлы"]])
        self.assertTrue(all(len(item["sha"]) == 12 for item in pack["файлы"]))
        self.assertEqual(1, built["инструкций"])
        self.assertIsNone(pack["расширяет"])

    def test_track_without_pack_has_null(self):
        built, errors = self.errors()
        self.assertEqual([], errors)
        self.assertIsNone(built["направления"][0]["инструкции"])
        self.assertEqual(0, built["инструкций"])

    def test_unknown_and_missing_fields(self):
        _, errors = self.errors(profile=dict(self.GOOD, лишнее=1))
        self.assertTrue(any("неизвестное поле «лишнее»" in e for e in errors), errors)
        bad = dict(self.GOOD)
        del bad["имена"]
        _, errors = self.errors(profile=bad)
        self.assertTrue(any("«имена»" in e for e in errors), errors)

    def test_value_formats(self):
        for key, value, marker in (("имена", ["Бухгалтерия предприятия"], "пробел"),
                                   ("имена", [], "непустой"),
                                   ("семейство", "БП", "латиница"),
                                   ("мин_версия", "3", "3.0.150"),
                                   ("синоним_re", "(", "не компилируется"),
                                   ("признаки", {"бухгалтерия": "да"}, "булев"),
                                   ("признаки", {"прочее": True}, "неизвестный признак"),
                                   ("поставщики", "Фирма", "список строк"),
                                   ("расширяет", "bp", "само себя")):
            _, errors = self.errors(profile=dict(self.GOOD, **{key: value}))
            self.assertTrue(any(marker in e for e in errors), (key, value, errors))

    def test_pack_files_need_profile_but_objects_md_does_not(self):
        _, errors = self.errors(files={"objects.md": "карта\n"})
        self.assertEqual([], errors)
        _, errors = self.errors(files={"notes.md": "заметка\n"})
        self.assertTrue(any("без profile.json" in e for e in errors), errors)

    def test_chips_schema(self):
        for text, marker in ('{"a": 1}', "список"), ('[{"id": "a"}]', "«заголовок»"), \
                            ('[{"id": "a", "заголовок": "б", "текст": "в", "x": 1}]', "неизвестное поле"), \
                            ('[{"id": "a", "заголовок": "б", "текст": "в"}, {"id": "a", "заголовок": "б", "текст": "в"}]', "повторяется"), \
                            ("[", "не JSON"):
            _, errors = self.errors(profile=self.GOOD, files={"chips.json": text})
            self.assertTrue(any(marker in e for e in errors), (text, errors))

    def test_extends_must_point_to_pack(self):
        _, errors = self.errors(profile=dict(self.GOOD, расширяет="ut"), extra_tracks=(("ut", "типовая"),))
        self.assertTrue(any("нет пакета с profile.json" in e for e in errors), errors)
        _, errors = self.errors(profile=dict(self.GOOD, расширяет="нет"))
        self.assertTrue(any("«нет»" in e for e in errors), errors)

    def test_size_ceiling(self):
        _, errors = self.errors(profile=self.GOOD, files={"notes.md": "я" * (manifest.PACK_LIMIT // 2 + 1)})
        self.assertTrue(any("больше потолка" in e for e in errors), errors)

    def test_template_dir_is_skipped_and_fixture_is_valid(self):
        built, errors = manifest.collect()
        self.assertEqual([], errors)
        self.assertNotIn("_PACK_TEMPLATE", [t["код"] for t in built["направления"]])
        fixture = os.path.join(ROOT, "tests", "fixtures", "knowledge")
        built, errors = manifest.collect(root=fixture)
        self.assertEqual([], errors)
        self.assertEqual(["ut"], [t["инструкции"]["расширяет"] for t in built["направления"]
                                  if t["код"] == "ka"])
        with open(os.path.join(fixture, "manifest.json"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), manifest.render(built), "пересобрать: scripts/manifest.py --корень tests/fixtures/knowledge")

    def test_root_option(self):
        self.assertEqual(os.path.abspath("x"), manifest.parse_root(["--корень", "x"]))
        self.assertEqual(os.path.abspath("y"), manifest.parse_root(["--проверить", "--root=y"]))
        self.assertIsNone(manifest.parse_root(["--проверить"]))


if __name__ == "__main__":
    unittest.main()
