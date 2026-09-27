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


def command(placement, tail):
    """Карточка команды размещения по хвосту имени («StandardCommand.OpenList»)."""
    found = [item for item in placement["команды"]
             if item["команда_метаданных"].endswith("." + tail)]
    return found[0] if found else None


class WhereIsFixture(unittest.TestCase):

    def ask(self, query, **kwargs):
        kwargs.setdefault("manifest", TEST_MANIFEST)
        return dump.where_is(FIXTURE, query, **kwargs)

    def one(self, query, **kwargs):
        result = self.ask(query, **kwargs)
        self.assertEqual(1, len(result["объекты"]), result)
        return result["объекты"][0]

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
        repair = command(sections["Ремонт"], "StandardCommand.OpenList")
        self.assertEqual(["Кладовщик"], repair["видимость"]["роли_скрыто"])
        self.assertTrue(repair["видимость"]["по_умолчанию"])
        self.assertEqual("Список", sections["Ремонт"]["открыть_командой"]["команда"])
        stock = command(sections["Склад запчастей"], "StandardCommand.OpenList")
        self.assertEqual([], stock["видимость"]["роли_скрыто"])
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
        # Раздел «Склад запчастей» тоже совпал по синониму.
        self.assertEqual(["Подсистема.Склад"],
                         [item["подсистема"] for item in result["разделы"]])

    def test_short_name(self):
        card = self.one("ЗаявкаНаРемонт")
        self.assertEqual("Документ.ЗаявкаНаРемонт", card["полное_имя"])
        self.assertEqual("имя", card["совпадение"])

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
        placement = self.one("ЛистДиагностики")["размещения"][0]
        self.assertEqual("Ремонт", placement["раздел"])
        self.assertEqual(["Ремонт", "Диагностика"], placement["путь"])
        self.assertEqual("Подсистема.Ремонт.Подсистема.Диагностика", placement["подсистема"])
        self.assertTrue(placement["в_командном_интерфейсе"])

    def test_report_visible_only_to_role(self):
        result = self.ask("Отчёт.ЗагрузкаМастеров")
        golden(self, "report", result)
        card = result["объекты"][0]
        visibility = command(card["размещения"][0], "StandardCommand.Open")["видимость"]
        self.assertFalse(visibility["по_умолчанию"])
        self.assertEqual(["Мастер"], visibility["роли_видят"])  # в XML записано «Роль.Мастер»
        self.assertTrue(card["размещения"][0]["в_командном_интерфейсе"])
        self.assertEqual("e1cib/app/Отчет.ЗагрузкаМастеров", card["навигационная_ссылка"])

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
        self.assertFalse(placement["подсистема_в_интерфейсе"])
        self.assertFalse(placement["в_командном_интерфейсе"])
        self.assertIn("Служебные", card["примечание"])

    def test_nothing_found(self):
        result = self.ask("Документ.НетТакого")
        self.assertEqual(0, result["найдено"])
        self.assertEqual([], result["объекты"])
        self.assertIn("подсказка", result)

    def test_empty_query_rejected(self):
        with self.assertRaises(dump.DumpError):
            self.ask("   ")

    # --- команды объекта ----------------------------------------------------

    def test_own_command_opens_when_standard_list_hidden(self):
        result = self.ask("Документ.ЗаявкаНаРемонт")
        golden(self, "own_command", result)
        placement = result["объекты"][0]["размещения"][0]
        self.assertFalse(command(placement, "StandardCommand.OpenList")["видимость"]["по_умолчанию"])
        opener = placement["открыть_командой"]
        self.assertEqual("Заявки в работе", opener["команда"])
        self.assertEqual("Панель навигации: Обычное", opener["группа"])
        self.assertTrue(placement["в_командном_интерфейсе"])
        own = command(placement, "Command.ОткрытьЗаявкиВРаботе")
        self.assertEqual("e1cib/command/Документ.ЗаявкаНаРемонт.Команда.ОткрытьЗаявкиВРаботе",
                         own["ссылка"])
        self.assertEqual(["Использовать диагностику"], own["функциональные_опции"])
        # Команда формы (с параметром, группа FormCommandBar…) в раздел не попадает.
        self.assertIsNone(command(placement, "Command.СоздатьАкт"))

    def test_command_groups(self):
        act = by_section(self.one("Документ.АктВыполненныхРабот"))["Ремонт"]
        # CommandsPlacement важнее CommandsOrder.
        self.assertEqual("Панель навигации: Важное",
                         command(act, "StandardCommand.OpenList")["группа"])
        bikes = by_section(self.one("Справочник.Велосипеды"))["Ремонт"]
        self.assertEqual("Панель навигации: См. также",
                         command(bikes, "StandardCommand.OpenList")["группа"])
        picker = self.one("Обработка.ПодборЗапчастей")["размещения"][0]
        self.assertEqual("Группа «Инструменты мастерской» (панель действий)",
                         picker["открыть_командой"]["группа"])

    def test_create_is_not_a_way_to_find(self):
        bikes = by_section(self.one("Справочник.Велосипеды"))["Ремонт"]
        self.assertEqual("Панель действий: Создать",
                         command(bikes, "StandardCommand.Create")["группа"])
        self.assertIsNone(bikes["открыть_командой"])
        self.assertFalse(bikes["в_командном_интерфейсе"])

    def test_default_visibility_unknown_for_accumulation_register(self):
        card = self.one("РегистрНакопления.ОстаткиЗапчастей")
        placement = card["размещения"][0]
        view = command(placement, "StandardCommand.OpenList")["видимость"]
        self.assertIsNone(view["по_умолчанию"])
        self.assertEqual("не указана в выгрузке", view["источник"])
        self.assertIsNone(placement["в_командном_интерфейсе"])
        self.assertIn("не определить", card["примечание"])

    def test_default_visibility_confirmed_for_catalog(self):
        placement = self.one("Справочник.Запчасти")["размещения"][0]
        view = command(placement, "StandardCommand.OpenList")["видимость"]
        self.assertTrue(view["по_умолчанию"])
        self.assertEqual("умолчание платформы", view["источник"])

    def test_use_standard_commands_false(self):
        card = self.one("Справочник.ВидыРабот")
        self.assertFalse(card["стандартные_команды"])
        placement = card["размещения"][0]
        self.assertEqual([], placement["команды"])
        self.assertFalse(placement["в_командном_интерфейсе"])
        self.assertIn("стандартные выключены", card["примечание"])

    def test_report_without_commands_mentions_panel(self):
        card = self.one("Отчет.СводкаРемонтов")
        self.assertFalse(card["стандартные_команды"])
        self.assertIn("панелью отчётов", card["примечание"])

    def test_rights_by_kind(self):
        bikes = self.one("Справочник.Велосипеды")["права"]
        self.assertEqual(["Мастер"], bikes["просмотр"]["роли"])
        self.assertEqual(["Кладовщик", "Мастер"], bikes["чтение"]["роли"])
        report = self.one("Отчет.ЗагрузкаМастеров")["права"]
        self.assertEqual(["Мастер"], report["использование"]["роли"])
        self.assertNotIn("чтение", report)
        picker = self.one("Обработка.ПодборЗапчастей")["права"]
        self.assertEqual(["Кладовщик"], picker["использование"]["роли"])
        self.assertEqual(0, picker["просмотр"]["всего"])

    def test_section_hidden_for_role_by_configuration(self):
        placement = self.one("Справочник.Запчасти")["размещения"][0]
        self.assertEqual(["Мастер"], placement["видимость_раздела"]["роли_скрыто"])
        self.assertEqual("командный интерфейс", placement["видимость_раздела"]["источник"])

    def test_functional_option_on_object(self):
        card = self.one("Документ.ЛистДиагностики")
        self.assertEqual(["Использовать диагностику"], card["функциональные_опции"])
        self.assertIn("функциональные опции", card["оговорка"])

    def test_common_command(self):
        result = self.ask("этикет")
        golden(self, "common_command", result)
        card = result["объекты"][0]
        self.assertEqual("ОбщаяКоманда.ПечатьЭтикеток", card["полное_имя"])
        self.assertEqual("e1cib/command/ОбщаяКоманда.ПечатьЭтикеток", card["навигационная_ссылка"])
        self.assertEqual("Панель действий: Сервис",
                         card["размещения"][0]["открыть_командой"]["группа"])
        self.assertEqual(["Кладовщик"], card["права"]["просмотр"]["роли"])

    def test_section_by_title(self):
        result = self.ask("Склад запчастей")
        golden(self, "section", result)
        self.assertEqual([], result["объекты"])
        section = result["разделы"][0]
        self.assertEqual("Подсистема.Склад", section["подсистема"])
        self.assertEqual(["Мастер"], section["видимость_раздела"]["роли_скрыто"])
        names = [item["полное_имя"] for item in section["состав"]]
        self.assertIn("Документ.АктВыполненныхРабот", names)
        self.assertIn("ОбщаяКоманда.ПечатьЭтикеток", names)
        self.assertEqual(len(names), section["состав_всего"])

    def test_section_by_full_name(self):
        result = self.ask("Подсистема.Ремонт.Подсистема.Диагностика")
        section = result["разделы"][0]
        self.assertEqual(["Ремонт", "Диагностика"], section["путь"])
        self.assertEqual(["Документ.ЛистДиагностики"],
                         [item["полное_имя"] for item in section["состав"]])
        self.assertEqual(["Диагностика"], self.ask("Подсистема.Ремонт")["разделы"][0]["подразделы"])


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
        # Ссылка внутрь выгрузки на уже прочитанную подсистему — повтор, не второй раздел.
        os.remove(os.path.join(self.dump, "Subsystems", "Внешняя.xml"))
        os.symlink(os.path.join(self.dump, "Subsystems", "Склад.xml"),
                   os.path.join(self.dump, "Subsystems", "Внешняя.xml"))
        os.utime(os.path.join(self.dump, "Configuration.xml"), None)
        dump._CACHE.clear()
        parts = dump.where_is(self.dump, "Справочник.Запчасти", manifest=TEST_MANIFEST)
        self.assertEqual(1, len(parts["объекты"][0]["размещения"]))
        self.assertTrue(any("уже прочитана" in item for item in parts["предупреждения"]))
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


class DumpFormats(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tiny1c-")
        self.dump = os.path.join(self.tmp, "dump")
        shutil.copytree(FIXTURE, self.dump)

    def tearDown(self):
        shutil.rmtree(self.tmp)
        dump._CACHE.clear()

    def replace(self, rel, old, new):
        path = os.path.join(self.dump, rel)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(old, text)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(old, new))

    def test_plain_format_by_dump_info_is_rejected(self):
        self.replace("ConfigDumpInfo.xml", 'format="Hierarchical"', 'format="Plain"')
        with self.assertRaises(dump.DumpError) as caught:
            dump.where_is(self.dump, "акт", manifest=TEST_MANIFEST)
        self.assertIn("Plain", str(caught.exception))

    def test_plain_format_by_file_names_is_rejected(self):
        os.remove(os.path.join(self.dump, "ConfigDumpInfo.xml"))
        shutil.copy(os.path.join(self.dump, "Catalogs", "Запчасти.xml"),
                    os.path.join(self.dump, "Catalog.Запчасти.xml"))
        with self.assertRaises(dump.DumpError) as caught:
            dump.where_is(self.dump, "акт", manifest=TEST_MANIFEST)
        self.assertIn("Plain", str(caught.exception))

    def test_english_script_variant_links(self):
        self.replace("Configuration.xml", "<ScriptVariant>Russian</ScriptVariant>",
                     "<ScriptVariant>English</ScriptVariant>")
        card = dump.where_is(self.dump, "ЗаявкаНаРемонт", manifest=TEST_MANIFEST)["объекты"][0]
        self.assertEqual("e1cib/list/Document.ЗаявкаНаРемонт", card["навигационная_ссылка"])
        own = command(card["размещения"][0], "Command.ОткрытьЗаявкиВРаботе")
        self.assertEqual("e1cib/command/Document.ЗаявкаНаРемонт.Command.ОткрытьЗаявкиВРаботе",
                         own["ссылка"])

    def test_cache_follows_config_dump_info(self):
        first = dump.load_index(self.dump)
        self.replace("ConfigDumpInfo.xml", "</ConfigVersions>",
                     '\t<Metadata name="Catalog.Новый" id="x"/>\n\t</ConfigVersions>')
        self.assertIsNot(first, dump.load_index(self.dump))
