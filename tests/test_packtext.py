# -*- coding: utf-8 -*-
"""Сжатие текста пакета для промпта (mcp/packtext.py) и настоящий пакет bp: что уходит помощнику, что нет."""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mcp"))
import packtext  # noqa: E402
from tests import knowledge_fixture as kf  # noqa: E402

manifest = kf.load_module("tiny1c_manifest_packtext", "scripts", "manifest.py")
instructions = kf.load_module("tiny1c_instructions_packtext", "mcp", "instructions.py")

SAMPLE = """# Заголовок файла

Вступление для помощника (S-3).

## Раздел

| что | путь | как открыть | статус |
|---|---|---|---|
| Выписки | Банк › Выписки | list:Документ.Выписка | S-3 |
| Касса | Банк › Касса | — | [проверить] |

- Тезис с источником (S-5, S-6; с 3.0.144).
- Тезис из опыта (опыт).
- Неподтверждённый тезис [проверить] из форума.

## Детали (подробно)

- Этого в промпте нет.

### Подраздел деталей

- И этого тоже.

## Снова в промпт

- Последний тезис (из промпта).
"""


class PromptText(unittest.TestCase):

    def test_rules(self):
        text = packtext.prompt_text(SAMPLE)
        self.assertNotIn("Заголовок файла", text)
        self.assertIn("Вступление для помощника.", text)
        self.assertIn("| что | путь | как открыть |", text)
        self.assertIn("| Выписки | Банк › Выписки | list:Документ.Выписка |", text)
        self.assertNotIn("статус", text)
        self.assertNotIn("Касса", text)
        self.assertIn("- Тезис с источником.", text)
        self.assertIn("- Тезис из опыта.", text)
        self.assertNotIn("Неподтверждённый", text)
        self.assertNotIn("подробно", text)
        self.assertNotIn("Этого в промпте нет", text)
        self.assertNotIn("И этого тоже", text)
        self.assertIn("## Снова в промпт", text)
        self.assertIn("- Последний тезис.", text)
        self.assertNotIn("\n\n\n", text)
        self.assertFalse(text.endswith("\n"))

    def test_demote(self):
        self.assertEqual("### A\nтекст\n#### B", packtext.demote("## A\nтекст\n### B"))

    def test_table_without_status_column_untouched(self):
        text = packtext.prompt_text("| а | б |\n|---|---|\n| 1 | 2 |\n")
        self.assertEqual("| а | б |\n| --- | --- |\n| 1 | 2 |", text)


class RealBpPack(unittest.TestCase):
    """Настоящий пакет tracks/bp: потолок промпта и чистота текста."""

    @classmethod
    def setUpClass(cls):
        cls.snap = kf.snapshot_of(ROOT)

    def test_prompt_is_clean_and_within_limit(self):
        result = instructions.tool_get_instructions(self.snap, {"track": "bp"})
        self.assertNotIn("ошибка", result)
        text = result["текст"]
        self.assertLessEqual(result["размер"], manifest.PROMPT_LIMIT)
        for marker in ("[проверить]", "(S-", "| статус", "(подробно)", "Для ревью", "http://", "https://", "<"):
            self.assertNotIn(marker, text, marker)
        self.assertIn("## Конфигурация", text)
        self.assertIn("### Коротко", text)
        self.assertIn("Операции › Закрытие периода › Закрытие месяца", text)
        self.assertNotIn("Документ.ПоступлениеТоваровУслуг ✓", text)   # objects.md — по запросу
        self.assertEqual(["faq.md", "objects.md"], result["файлы_по_запросу"])
        ids = [chip["id"] for chip in result["чипы"]]
        self.assertEqual("u-orgs", ids[0])                   # общие чипы core первыми
        self.assertIn("bp-osv", ids)
        self.assertNotIn("bp-month", ids)                    # чип с «проверить» не отдаётся
        self.assertTrue(all("тема" in chip for chip in result["чипы"]))

    def test_manifest_sizes(self):
        track = [t for t in self.snap["направления"] if t["код"] == "bp"][0]["инструкции"]
        self.assertLessEqual(track["размер_промпта"], manifest.PROMPT_LIMIT)
        self.assertLessEqual(track["размер"], manifest.PACK_LIMIT)
        core = [t for t in self.snap["направления"] if t["код"] == "core"][0]["инструкции"]
        self.assertEqual(["accounting", "accumulation", "calculation", "queries"],
                         [c["имя"] for c in core["шпаргалки"]])
        self.assertLessEqual(core["размер_шпаргалок"], manifest.CHEATS_LIMIT)

    def test_match_real_bp(self):
        for name in ("БухгалтерияПредприятия", "БухгалтерияПредприятияКОРП"):
            result = instructions.tool_match_config(self.snap, {"name": name, "version": "3.0.165.20",
                                                                "vendor": 'Фирма "1С"'})
            self.assertEqual("bp", result["направление"], name)
            self.assertTrue(result["поставщик_совпадает"])
            self.assertTrue(result["версия_поддерживается"])
        result = instructions.tool_match_config(self.snap, {"name": "Своя", "synonym": "Бухгалтерия предприятия, редакция 3.0"})
        self.assertEqual("bp", result["направление"])
        self.assertFalse(instructions.tool_match_config(self.snap, {"name": "БухгалтерияПредприятия",
                                                                    "version": "3.0.100"})["версия_поддерживается"])

    def test_cheats_are_verbatim_prompts(self):
        result = instructions.tool_get_cheats(self.snap, {})
        self.assertEqual(4, len(result["шпаргалки"]))
        accounting = [c for c in result["шпаргалки"] if c["имя"] == "accounting"][0]
        self.assertIn("%ПланСчетов%", accounting["текст"])
        self.assertIn("%ВидыСубконто%", accounting["текст"])
        self.assertTrue(all(c["текст"].count("\n---") == 0 for c in result["шпаргалки"]))  # без фронтматтера

    def test_sources_are_outside_the_pack(self):
        track = [t for t in self.snap["направления"] if t["код"] == "bp"][0]["инструкции"]
        self.assertNotIn("sources.md", [f["имя"] for f in track["файлы"]])
        with open(os.path.join(ROOT, "tracks", "bp", "sources.md"), encoding="utf-8") as handle:
            self.assertIn("https://", handle.read())
        for name in ("where_is.md", "notes.md", "objects.md", "faq.md", "chips.json"):
            with open(os.path.join(ROOT, "tracks", "bp", name), encoding="utf-8") as handle:
                self.assertNotIn("http", handle.read(), name)
        chips = json.load(open(os.path.join(ROOT, "tracks", "bp", "chips.json"), encoding="utf-8"))
        self.assertTrue(any(chip.get("проверить") for chip in chips))


if __name__ == "__main__":
    unittest.main()
