# -*- coding: utf-8 -*-
"""where_is на синтетической выгрузке fixtures/dump-mini.

Golden-ответы лежат в tests/golden/where_is_*.json и сравниваются с реальным
выводом целиком. Пересобрать их после осознанной смены формата ответа:
  TINY1C_UPDATE_GOLDEN=1 python3 scripts/tools-check.py
и просмотреть diff глазами — golden не должен повторять ошибку кода.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mcp"))

from tools import dump  # noqa: E402

FIXTURE = os.path.join(ROOT, "fixtures", "dump-mini")
GOLDEN = os.path.join(ROOT, "tests", "golden")
UPDATE = os.environ.get("TINY1C_UPDATE_GOLDEN") == "1"

# Подменный глоссарий: реальные глоссарии ради теста не правятся.
TEST_MANIFEST = {
    "направления": [
        {"код": "тест", "глоссарий": [
            {"термин": "Выдача велосипеда", "синонимы": ["сдача работ"],
             "объекты": ["Документ.АктВыполненныхРабот", "Документ.НетВВыгрузке"],
             "пояснение": "документ, которым мастер отдаёт велосипед клиенту"},
            {"термин": "Карточка ремонта", "синонимы": [],
             "объекты": ["форма документа"], "пояснение": "не объект метаданных"},
        ]},
        {"код": "другое", "глоссарий": [
            {"термин": "Выдача велосипеда", "синонимы": [],
             "объекты": ["Справочник.Велосипеды"], "пояснение": "в другом направлении"},
        ]},
    ],
}


def golden(test, name, result):
    path = os.path.join(GOLDEN, "where_is_%s.json" % name)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if UPDATE:
        os.makedirs(GOLDEN, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    with open(path, encoding="utf-8") as handle:
        expected = json.load(handle)
    test.assertEqual(expected, json.loads(text), "расходится с %s" % os.path.relpath(path, ROOT))


def by_section(card):
    return {item["раздел"]: item for item in card["размещения"]}


class WhereIsFixture(unittest.TestCase):

    def ask(self, query, **kwargs):
        kwargs.setdefault("manifest", TEST_MANIFEST)
        return dump.where_is(FIXTURE, query, **kwargs)

    def test_full_name_two_sections_and_role_hidden(self):
        result = self.ask("Документ.АктВыполненныхРабот")
        golden(self, "full_name", result)
        self.assertEqual(1, result["найдено"])
        card = result["объекты"][0]
        sections = by_section(card)
        # «Склад запчастей» лежит в файле с BOM — пропадёт, если BOM сломает разбор.
        self.assertEqual({"Ремонт", "Склад запчастей"}, set(sections))
        # В синониме два языка, английский первым — отдаётся русский.
        self.assertEqual("Акт выполненных работ", card["синоним"])
        self.assertEqual(["Кладовщик"], sections["Ремонт"]["видимость"]["роли_скрыто"])
        self.assertTrue(sections["Ремонт"]["видимость"]["по_умолчанию"])
        self.assertEqual([], sections["Склад запчастей"]["видимость"]["роли_скрыто"])
        self.assertEqual("Список", sections["Ремонт"]["команда"])
        self.assertEqual("e1cib/list/Документ.АктВыполненныхРабот", card["навигационная_ссылка"])
        self.assertNotIn("примечание", card)

    def test_english_full_name_is_same_object(self):
        ru = self.ask("Документ.АктВыполненныхРабот")["объекты"]
        en = self.ask("document.АктВыполненныхРабот")["объекты"]
        self.assertEqual(ru, en)

    def test_full_name_wins_over_synonym(self):
        # «Справочник.Запчасти» — только он, без обработки и регистра с тем же словом.
        result = self.ask("Справочник.Запчасти")
        self.assertEqual(["Справочник.Запчасти"],
                         [card["полное_имя"] for card in result["объекты"]])

    def test_synonym_substring(self):
        result = self.ask("ЗАПЧАСТ")
        golden(self, "synonym", result)
        self.assertEqual(
            ["Обработка.ПодборЗапчастей", "РегистрНакопления.ОстаткиЗапчастей",
             "Справочник.Запчасти"],
            [card["полное_имя"] for card in result["объекты"]])
        processor = result["объекты"][0]
        self.assertEqual("e1cib/app/Обработка.ПодборЗапчастей", processor["навигационная_ссылка"])
        self.assertEqual("Открыть", processor["размещения"][0]["команда"])

    def test_short_name(self):
        result = self.ask("ЗаявкаНаРемонт")
        self.assertEqual(["Документ.ЗаявкаНаРемонт"],
                         [card["полное_имя"] for card in result["объекты"]])
        self.assertEqual("имя", result["объекты"][0]["совпадение"])

    def test_glossary_term(self):
        result = self.ask("сдача работ", track="тест")
        golden(self, "glossary", result)
        self.assertEqual(["Документ.АктВыполненныхРабот"],
                         [card["полное_имя"] for card in result["объекты"]])
        self.assertTrue(result["объекты"][0]["совпадение"].startswith("глоссарий:"))
        self.assertEqual(["Документ.НетВВыгрузке"],
                         [item["объект"] for item in result["термины_без_объектов"]])

    def test_track_narrows_glossary(self):
        both = self.ask("выдача велосипеда")
        only = self.ask("выдача велосипеда", track="тест")
        self.assertEqual({"Документ.АктВыполненныхРабот", "Справочник.Велосипеды"},
                         {card["полное_имя"] for card in both["объекты"]})
        self.assertEqual({"Документ.АктВыполненныхРабот"},
                         {card["полное_имя"] for card in only["объекты"]})

    def test_real_glossary_term_absent_in_dump(self):
        result = dump.where_is(FIXTURE, "расходная накладная", track="unf")
        self.assertEqual([], result["объекты"])
        self.assertIn("подсказка", result)
        self.assertIn("Документ.РасходнаяНакладная",
                      [item["объект"] for item in result["термины_без_объектов"]])

    def test_nested_subsystem_path(self):
        card = self.ask("ЛистДиагностики")["объекты"][0]
        placement = card["размещения"][0]
        self.assertEqual("Ремонт", placement["раздел"])
        self.assertEqual(["Ремонт", "Диагностика"], placement["путь"])
        self.assertEqual("Подсистема.Ремонт.Подсистема.Диагностика", placement["подсистема"])
        self.assertTrue(placement["в_командном_интерфейсе"])

    def test_report_visible_only_to_role(self):
        result = self.ask("Отчёт.ЗагрузкаМастеров")
        golden(self, "report", result)
        card = result["объекты"][0]
        visibility = card["размещения"][0]["видимость"]
        self.assertFalse(visibility["по_умолчанию"])
        self.assertEqual(["Мастер"], visibility["роли_видят"])  # в XML записано «Роль.Мастер»
        self.assertEqual("e1cib/app/Отчет.ЗагрузкаМастеров", card["навигационная_ссылка"])
        self.assertEqual(["Мастер"], card["права"]["просмотр"])

    def test_object_outside_subsystems(self):
        result = self.ask("причины отказа")
        golden(self, "outside", result)
        card = result["объекты"][0]
        self.assertEqual([], card["размещения"])
        self.assertIn("Все функции", card["примечание"])
        self.assertEqual("e1cib/list/Справочник.ПричиныОтказа", card["навигационная_ссылка"])

    def test_subsystem_excluded_from_command_interface(self):
        result = self.ask("НастройкиМастерской")
        golden(self, "hidden_subsystem", result)
        card = result["объекты"][0]
        placement = card["размещения"][0]
        # Сама подсистема «Администрирование» включена, но скрыт её предок.
        self.assertEqual(["Служебные", "Администрирование"], placement["путь"])
        self.assertFalse(placement["в_командном_интерфейсе"])
        self.assertIn("Служебные", card["примечание"])

    def test_rights(self):
        card = self.ask("Справочник.Велосипеды")["объекты"][0]
        self.assertEqual(["Мастер"], card["права"]["просмотр"])
        self.assertEqual(["Кладовщик", "Мастер"], card["права"]["чтение"])

    def test_nothing_found(self):
        result = self.ask("Документ.НетТакого")
        self.assertEqual(0, result["найдено"])
        self.assertEqual([], result["объекты"])
        self.assertIn("подсказка", result)

    def test_empty_query_rejected(self):
        with self.assertRaises(dump.DumpError):
            self.ask("   ")


class DumpBoundaries(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tiny1c-")
        self.dump = os.path.join(self.tmp, "dump")
        shutil.copytree(FIXTURE, self.dump)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def add_to_configuration(self, element):
        path = os.path.join(self.dump, "Configuration.xml")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        text = text.replace("\t\t</ChildObjects>", "\t\t\t%s\n\t\t</ChildObjects>" % element)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_dump_must_exist_and_have_configuration(self):
        for bad in ("", os.path.join(self.tmp, "нет"), self.tmp,
                    os.path.join(FIXTURE, ".."), os.path.join(FIXTURE, "Documents")):
            with self.assertRaises(dump.DumpError, msg=bad):
                dump.where_is(bad, "акт", manifest=TEST_MANIFEST)

    def test_dotdot_in_object_name_is_not_followed(self):
        outside = os.path.join(self.tmp, "Секрет.xml")
        shutil.copy(os.path.join(self.dump, "Documents", "ЗаявкаНаРемонт.xml"), outside)
        self.add_to_configuration("<Document>../../Секрет</Document>")
        self.add_to_configuration("<Subsystem>..</Subsystem>")
        result = dump.where_is(self.dump, "заявка", manifest=TEST_MANIFEST)
        self.assertEqual(["Документ.ЗаявкаНаРемонт"],
                         [card["полное_имя"] for card in result["объекты"]])
        self.assertTrue(any("не годится для пути" in item for item in result["предупреждения"]))

    @unittest.skipIf(not hasattr(os, "symlink"), "нет символических ссылок")
    def test_symlink_outside_dump_is_not_read(self):
        outside = os.path.join(self.tmp, "Утечка.xml")
        with open(os.path.join(self.dump, "Documents", "ЗаявкаНаРемонт.xml"),
                  encoding="utf-8") as handle:
            text = handle.read().replace("Заявка на ремонт", "СЕКРЕТНЫЙ СИНОНИМ")
        with open(outside, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.symlink(outside, os.path.join(self.dump, "Documents", "Утечка.xml"))
        self.add_to_configuration("<Document>Утечка</Document>")
        shutil.copy(os.path.join(self.dump, "Subsystems", "Склад.xml"),
                    os.path.join(self.tmp, "Внешняя.xml"))
        os.symlink(os.path.join(self.tmp, "Внешняя.xml"),
                   os.path.join(self.dump, "Subsystems", "Внешняя.xml"))
        self.add_to_configuration("<Subsystem>Внешняя</Subsystem>")

        result = dump.where_is(self.dump, "секретный", manifest=TEST_MANIFEST)
        self.assertEqual([], result["объекты"])
        warnings = result["предупреждения"]
        self.assertTrue(any("Documents/Утечка.xml" in item and "за пределы" in item
                            for item in warnings), warnings)
        self.assertTrue(any("Subsystems/Внешняя.xml" in item for item in warnings), warnings)
        # Подсистема снаружи не прочитана: у каталога запчастей один раздел, а не два.
        parts = dump.where_is(self.dump, "Справочник.Запчасти", manifest=TEST_MANIFEST)
        self.assertEqual(["Склад запчастей"],
                         [item["раздел"] for item in parts["объекты"][0]["размещения"]])
        # Ссылка, которая ведёт обратно внутрь выгрузки, законна.
        os.remove(os.path.join(self.dump, "Subsystems", "Внешняя.xml"))
        os.symlink(os.path.join(self.dump, "Subsystems", "Склад.xml"),
                   os.path.join(self.dump, "Subsystems", "Внешняя.xml"))
        os.utime(os.path.join(self.dump, "Configuration.xml"), None)
        dump._CACHE.clear()
        parts = dump.where_is(self.dump, "Справочник.Запчасти", manifest=TEST_MANIFEST)
        self.assertEqual(2, len(parts["объекты"][0]["размещения"]))
        # Объект есть, но синоним из внешнего файла не прочитан.
        leaked = dump.where_is(self.dump, "Документ.Утечка", manifest=TEST_MANIFEST)
        self.assertEqual("", leaked["объекты"][0]["синоним"])

    def test_limit_twenty_and_truncation(self):
        template = os.path.join(self.dump, "Catalogs", "Запчасти.xml")
        with open(template, encoding="utf-8") as handle:
            text = handle.read()
        for number in range(25):
            name = "Набор%02d" % number
            with open(os.path.join(self.dump, "Catalogs", name + ".xml"), "w",
                      encoding="utf-8") as handle:
                handle.write(text.replace(">Запчасти<", ">%s<" % name, 1)
                             .replace("<v8:content>Запчасти", "<v8:content>Набор инструмента"))
            self.add_to_configuration("<Catalog>%s</Catalog>" % name)
        result = dump.where_is(self.dump, "набор инструмента", manifest=TEST_MANIFEST)
        self.assertEqual(25, result["найдено"])
        self.assertEqual(20, len(result["объекты"]))
        self.assertTrue(result["усечено"])

    def test_index_is_cached_and_rebuilt_on_change(self):
        first = dump.load_index(self.dump)
        self.assertIs(first, dump.load_index(self.dump))
        self.add_to_configuration("<Catalog>Новый</Catalog>")
        os.utime(os.path.join(self.dump, "Configuration.xml"), None)
        second = dump.load_index(self.dump)
        self.assertIsNot(first, second)
        self.assertIn("Catalog.Новый", second.objects)


if __name__ == "__main__":
    unittest.main()
