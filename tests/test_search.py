# -*- coding: utf-8 -*-
"""Поиск lookup_rule: golden-запросы на реальном наборе и разбор слов на синтетическом.

Реальные запросы взяты из жизни: дословные тексты ошибок 1С и слова, по которым
правила искали раньше. Ожидаемые id - это МИНИМУМ: набор растёт, и новое правило
вправе появиться в выдаче, но найденное прежде терять нельзя.
"""

import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mcp"))
SPEC = importlib.util.spec_from_file_location("tiny1c_server", os.path.join(ROOT, "mcp", "server.py"))
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)
import search  # noqa: E402

MANIFEST, _DIGEST = server.load_manifest()


def lookup(query, **extra):
    arguments = {"query": query}
    arguments.update(extra)
    return server.tool_lookup_rule(MANIFEST, arguments)


def ids(query, **extra):
    return [card["id"] for card in lookup(query, **extra).get("правила", [])]


class GoldenQueries(unittest.TestCase):

    # (запрос, id, которые обязаны найтись)
    CASES = [
        ("шапка", {"query-002", "forms-022"}),
        ("шапки", {"query-002", "forms-022"}),
        ("отчёт", {"query-005", "query-004", "query-006", "query-007", "workflow-002"}),
        ("отчет", {"query-005", "query-004", "workflow-014"}),
        ("Процедура или функция с указанным именем не определена",
         {"bsl-006", "bsl-015", "bsl-020", "workflow-011"}),
        ("недоступно для записи (Документы)", {"bsl-011", "bsl-028"}),
        ("Поле объекта недоступно для записи", {"bsl-011", "bsl-014", "bsl-008", "bsl-028"}),
        ("bsl-006", {"bsl-006"}),
        ("ЕстьNULL", {"bsl-006"}),
        ("естьnull", {"bsl-006"}),
        ("динамический список", {"bsl-013", "forms-008", "forms-009", "workflow-009", "forms-011",
                                 "forms-013", "forms-019"}),
        ("динамического списка", {"forms-009", "forms-011"}),
        ("ожидается )", {"bsl-001"}),
        ("глобальный контекст", {"bsl-001", "bsl-011", "bsl-028"}),
        ("коллизия имён", {"bsl-001", "bsl-011"}),
        ("печатная форма", {"tmpl-004", "workflow-014"}),
    ]

    def test_golden(self):
        for query, expected in self.CASES:
            found = set(ids(query))
            self.assertTrue(expected <= found, "%r: не нашлось %s" % (query, sorted(expected - found)))

    def test_word_forms_give_same_answer(self):
        self.assertEqual(set(ids("шапка")), set(ids("шапки")))
        self.assertEqual(set(ids("отчёт")), set(ids("отчет")))
        self.assertEqual(set(ids("динамический список")), set(ids("динамического списка")))

    def test_error_text_ranks_title_before_symptom(self):
        # bsl-015 назван этой ошибкой в заголовке и ключах, остальные - только в симптоме.
        found = ids("Процедура или функция с указанным именем не определена")
        self.assertEqual("bsl-015", found[0])
        self.assertLess(found.index("bsl-015"), found.index("workflow-011"))

    def test_id_query_returns_only_that_rule(self):
        self.assertEqual(["bsl-006"], ids("bsl-006"))
        self.assertEqual(["bsl-006"], ids("BSL-006"))

    def test_empty_query_is_error(self):
        for query in ("", "   "):
            self.assertIn("нужен запрос", lookup(query)["ошибка"])
        self.assertIn("ошибка", server.tool_lookup_rule(MANIFEST, {}))

    def test_nothing_found_is_empty_not_everything(self):
        result = lookup("zzzqqqxxx")
        self.assertEqual(0, result["найдено"])
        self.assertEqual([], result["правила"])

    def test_filters_and_limit(self):
        only_core = ids("шапка", track="core")
        self.assertTrue(only_core)
        self.assertEqual([], ids("шапка", track="нет-такого"))
        self.assertTrue(all(card["серьёзность"] == "критично"
                            for card in lookup("форма", severity="критично")["правила"]))
        limited = lookup("форма", limit=3)
        self.assertEqual(3, len(limited["правила"]))
        self.assertGreater(limited["найдено"], 3)
        self.assertEqual(3, limited["показано"])

    def test_default_limit_is_applied(self):
        result = lookup("bsl")  # часть id: правил много
        self.assertLessEqual(len(result["правила"]), server.DEFAULT_LIMIT)

    def test_symptom_is_in_manifest(self):
        with_symptom = [rule for rule in MANIFEST["правила"] if rule.get("симптом")]
        self.assertGreater(len(with_symptom), 50)
        self.assertTrue(all(len(rule["симптом"]) <= 700 for rule in with_symptom))


class Tokens(unittest.TestCase):

    def test_stem_merges_endings(self):
        for group in (("шапка", "шапки", "шапку"), ("отчёт", "отчет", "отчеты"),
                      ("динамический", "динамического", "динамическому")):
            self.assertEqual(1, len({search.stem(search.fold(word)) for word in group}), group)

    def test_punctuation_and_case(self):
        self.assertEqual(search.tokens("Документы"), search.tokens("(документы)"))
        self.assertEqual(["естьnull"], search.tokens("ЕстьNULL"))

    def test_short_words_share_stem(self):
        self.assertEqual(search.stem("поле"), search.stem("поля"))
        self.assertEqual(search.stem("поле"), search.stem("полей"))
        for word in ("тип", "код", "вид"):  # трёхбуквенные слова не режутся
            self.assertEqual(word, search.stem(word))
        self.assertNotEqual(search.stem("тип"), search.stem("тела"))

    def test_id_prefix_only_for_id_like_queries(self):
        self.assertEqual([], ids("-00"))
        self.assertEqual([], ids("sl-"))
        self.assertTrue(all(item.startswith("bsl-") for item in ids("bsl-0", limit=100)))
        self.assertTrue(ids("bsl", limit=100))

    def test_query_must_be_string(self):
        for bad in (["a"], 5, {"x": 1}):
            result = server.tool_lookup_rule(MANIFEST, {"query": bad})
            self.assertIn("строкой", result["ошибка"])

    def test_latin_and_digits_are_kept(self):
        self.assertEqual(["bsl", "006"], search.tokens("bsl-006"))


class Fallbacks(unittest.TestCase):

    RULES = [
        {"id": "t-001", "заголовок": "Первое правило", "ключи": ["альфа"], "серьёзность": "важно",
         "файл": "t-001"},
        {"id": "t-002", "заголовок": "Второе правило", "ключи": ["бета"], "серьёзность": "важно",
         "файл": "t-002", "симптом": "Видно слово гамма в симптоме"},
    ]
    BODIES = {"t-001": "Тело про уникальную дельту и эпсилон", "t-002": "пусто"}

    def index(self):
        return search.Index(self.RULES, lambda rule: self.BODIES[rule["файл"]])

    def test_body_fallback(self):
        rules, mode = self.index().search("уникальная дельта", lambda rule: True)
        self.assertEqual(["t-001"], [rule["id"] for rule in rules])
        self.assertEqual("по тексту", mode)

    def test_symptom_before_body(self):
        rules, mode = self.index().search("гамма", lambda rule: True)
        self.assertEqual(["t-002"], [rule["id"] for rule in rules])
        self.assertEqual("точный", mode)

    def test_partial_for_long_query(self):
        rules, mode = self.index().search("дельта эпсилон лишнее", lambda rule: True)
        self.assertEqual("частичный", mode)
        self.assertEqual(["t-001"], [rule["id"] for rule in rules])

    def test_missing_body_file_does_not_break_search(self):
        def boom(rule):
            raise FileNotFoundError(rule["id"])
        rules, _ = search.Index(self.RULES, boom).search("несуществующее", lambda rule: True)
        self.assertEqual([], rules)


if __name__ == "__main__":
    unittest.main()
