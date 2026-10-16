# -*- coding: utf-8 -*-
"""scripts/hygiene.py --файл: проверка одного правила вне дерева."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HYGIENE = os.path.join(ROOT, "scripts", "hygiene.py")
GOOD = """---
id: bsl-XXX
направление: core
категория: модули
серьёзность: важно
платформы: [8.5]
заголовок: "Тестовый заголовок"
ключи: [слово]
источник: "ошибка:проект 2026-10-01, где поймано"
check: ["manual:глазом"]
---

## Симптом

Текст ошибки.

## Причина

Потому что.

## Правило

Делать так.

## Как проверить

Глазами.
"""

GOOD_GUIDE = """---
id: how-XXX
направление: core
категория: расширения
платформы: [8.3, 8.5]
заголовок: "Тестовый рецепт"
источник: "практика:проект 2026-10-01, где проверено"
задача: "Получить тестовый результат"
ключи: [слово]
check: ["manual:глазом"]
правила: [ext-002]
---

## Шаги

1. Сделать раз.

## Проверка результата

Глазами.

## Где ломается

Не отмечено.
"""


class HygieneFile(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tiny1c-hyg-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_on(self, text):
        path = os.path.join(self.tmp, "bsl-XXX.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        done = subprocess.run([sys.executable, HYGIENE, "--файл", path], stdout=subprocess.PIPE,
                              timeout=30)
        return done.returncode, done.stdout.decode("utf-8")

    def test_good_file_passes(self):
        code, out = self.run_on(GOOD)
        self.assertEqual(0, code, out)

    def test_bad_values_fail(self):
        for old, new, mark in (
                ("категория: модули", "категория: выдумка", "категория"),
                ("check: [\"manual:глазом\"]", "check: [\"глазом\"]", "проверк"),
                ("источник: \"ошибка:проект 2026-10-01, где поймано\"", "источник: \"слышал\"", "источник"),
                ("Текст ошибки.", "Пишите на ivan@example.com", "почта"),
                ("Текст ошибки.", "Файл /Us" + "ers/ivan/work/x.bsl", "путь-mac"),
                ("Текст ошибки.", "паро" + "ль: 12345", "пароль"),
                ("id: bsl-XXX", "id: ЧТО-ТО", "id")):
            code, out = self.run_on(GOOD.replace(old, new))
            self.assertEqual(1, code, (old, out))
            self.assertIn(mark, out)

    def test_good_guide_passes(self):
        code, out = self.run_on(GOOD_GUIDE)
        self.assertEqual(0, code, out)

    def test_guide_is_checked_as_guide(self):
        # Без «источник» и «задача» рецепт - находка; серьёзность ему не нужна.
        code, out = self.run_on(GOOD_GUIDE.replace(
            'источник: "практика:проект 2026-10-01, где проверено"\n', ""))
        self.assertEqual(1, code, out)
        self.assertIn("источник", out)
        code, out = self.run_on(GOOD_GUIDE.replace("id: how-XXX", "id: bsl-XXX"))
        self.assertEqual(1, code, out)  # вид определяет «задача»: id правила рецепту не годится
        self.assertIn("how-001", out)
        code, out = self.run_on(GOOD_GUIDE.replace("id: how-XXX", "id: ЧТО-ТО"))
        self.assertEqual(1, code, out)
        code, out = self.run_on(GOOD_GUIDE.replace("правила: [ext-002]", "правила: [Что_то]"))
        self.assertEqual(1, code, out)

    def test_no_frontmatter_fails(self):
        self.assertEqual(1, self.run_on("просто текст")[0])

    def test_tree_mode_is_unchanged(self):
        done = subprocess.run([sys.executable, HYGIENE], stdout=subprocess.PIPE, timeout=60)
        self.assertEqual(0, done.returncode, done.stdout.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
