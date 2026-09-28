# -*- coding: utf-8 -*-
"""scripts/where-is-index.py на синтетической выгрузке fixtures/dump-mini.

Индекс — проекция карточек where_is: всё, что он говорит об объекте, обязано
совпадать с ответом where_is по тому же объекту.
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mcp"))

from tools import dump  # noqa: E402

FIXTURE = os.path.join(ROOT, "fixtures", "dump-mini")

_spec = importlib.util.spec_from_file_location(
    "where_is_index", os.path.join(ROOT, "scripts", "where-is-index.py"))
where_is_index = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(where_is_index)

TEST_MANIFEST = {
    "направления": [
        {"код": "тест", "глоссарий": [
            {"термин": "Выдача велосипеда", "синонимы": ["сдача работ"],
             "объекты": ["Документ.АктВыполненныхРабот", "Документ.НетВВыгрузке"]},
            {"термин": "Чужой термин", "синонимы": [], "объекты": ["Документ.НетВВыгрузке"]},
        ]},
        {"код": "другое", "глоссарий": [
            {"термин": "Велосипед клиента", "синонимы": [], "объекты": ["Справочник.Велосипеды"]},
        ]},
    ],
}


class WhereIsIndexTest(unittest.TestCase):

    def build(self, track=None):
        return where_is_index.build(FIXTURE, track, TEST_MANIFEST)

    def test_format_and_coverage(self):
        data = self.build()
        index = dump.load_index(FIXTURE)
        self.assertEqual(data["format"], "where_is_index_v1")
        self.assertEqual(data["конфигурация"]["имя"], "ВелоМастерская")
        self.assertEqual(len(data["объекты"]), len(index.objects))
        self.assertEqual(len(data["разделы"]), len(index.subsystems))
        # Индекс уходит в JSON целиком — без множеств и прочего несериализуемого.
        json.dumps(data, ensure_ascii=False)

    def test_object_matches_where_is(self):
        data = self.build()
        card = next(o for o in data["объекты"] if o["полное_имя"] == "Документ.ЗаявкаНаРемонт")
        answer = dump.where_is(FIXTURE, "Документ.ЗаявкаНаРемонт", manifest=TEST_MANIFEST)
        full = answer["объекты"][0]
        self.assertEqual(card["имя"], "ЗаявкаНаРемонт")
        self.assertEqual(card["синоним"], full["синоним"])
        self.assertEqual(card["ссылка"], full["навигационная_ссылка"])
        self.assertEqual(card["права"], full["права"])
        self.assertEqual(len(card["размещения"]), len(full["размещения"]))
        for mine, theirs in zip(card["размещения"], full["размещения"]):
            self.assertEqual(mine["путь"], theirs["путь"])
            self.assertEqual(mine["видно"], theirs["в_командном_интерфейсе"])
            self.assertEqual(mine["команда"], theirs["открыть_командой"]["команда"])
            self.assertEqual(mine["группа"], theirs["открыть_командой"]["группа"])
        # Собственная команда объекта, а не «Список»: стандартный список скрыт.
        self.assertEqual(card["размещения"][0]["команда"], "Заявки в работе")

    def test_hidden_roles_carried(self):
        data = self.build()
        card = next(o for o in data["объекты"] if o["полное_имя"] == "ОбщаяКоманда.ПечатьЭтикеток")
        place = card["размещения"][0]
        self.assertEqual(place["видимость_раздела"]["роли_скрыто"], ["Мастер"])
        self.assertNotIn("источник", place["видимость_раздела"])
        self.assertIn("примечание", card)

    def test_sections(self):
        data = self.build()
        section = next(s for s in data["разделы"] if s["подсистема"] == "Подсистема.Ремонт")
        self.assertEqual(section["имя"], "Ремонт")
        self.assertEqual(section["подразделы"], ["Диагностика"])
        names = [item["полное_имя"] for item in section["состав"]]
        self.assertIn("Документ.ЗаявкаНаРемонт", names)
        self.assertEqual(section["состав_всего"], len(section["состав"]))

    def test_glossary_only_present_objects(self):
        data = self.build()
        terms = {item["термин"]: item for item in data["глоссарий"]}
        self.assertEqual(terms["Выдача велосипеда"]["объекты"], ["Документ.АктВыполненныхРабот"])
        self.assertEqual(terms["Выдача велосипеда"]["синонимы"], ["сдача работ"])
        self.assertNotIn("Чужой термин", terms)
        self.assertIn("Велосипед клиента", terms)
        narrowed = {item["термин"] for item in self.build("тест")["глоссарий"]}
        self.assertEqual(narrowed, {"Выдача велосипеда"})

    def test_cli_rejects_non_dump(self):
        with tempfile.TemporaryDirectory() as empty:
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(where_is_index.main([empty]), 2)
            self.assertIn("Configuration.xml", err.getvalue())

    def test_cli_prints_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(where_is_index.main([FIXTURE]), 0)
        self.assertEqual(json.loads(out.getvalue())["format"], "where_is_index_v1")


if __name__ == "__main__":
    unittest.main()
