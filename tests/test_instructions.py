# -*- coding: utf-8 -*-
"""Группа instructions: match_config, get_instructions (с «расширяет»), get_cheats — на фикстуре знаний."""

import json
import unittest

from tests import knowledge_fixture as kf

server = kf.load_module("tiny1c_server_instr", "mcp", "server.py")
instructions = kf.load_module("tiny1c_instructions", "mcp", "instructions.py")


class Match(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tree = kf.fixture_copy(cls)
        cls.snap = kf.snapshot_of(cls.tree, revision="abc123")

    def match(self, **args):
        return instructions.tool_match_config(self.snap, args)

    def test_exact_name_wins(self):
        result = self.match(name="УправлениеТорговлей", version="11.5.10.100", vendor='Фирма "1С"')
        self.assertEqual("ut", result["направление"])
        self.assertEqual("имя", result["совпадение"])
        self.assertTrue(result["поставщик_совпадает"])
        self.assertTrue(result["версия_поддерживается"])

    def test_name_is_case_insensitive_and_vendor_normalized(self):
        result = self.match(name="комплекснаяавтоматизация", vendor="фирма 1с", version="2.4")
        self.assertEqual("ka", result["направление"])
        self.assertTrue(result["поставщик_совпадает"])
        self.assertFalse(result["версия_поддерживается"])
        self.assertEqual("2.5", result["кандидаты"][0]["мин_версия"])

    def test_synonym_regex_when_name_unknown(self):
        result = self.match(name="Моя", synonym="Управление торговлей, редакция 11")
        self.assertEqual("ut", result["направление"])
        self.assertEqual("синоним", result["совпадение"])
        self.assertIsNone(result["поставщик_совпадает"])
        self.assertIsNone(result["версия_поддерживается"])

    def test_foreign_vendor_is_reported_not_hidden(self):
        result = self.match(name="УправлениеТорговлей", vendor="ООО Ромашка")
        self.assertEqual("ut", result["направление"])
        self.assertFalse(result["поставщик_совпадает"])

    def test_unknown_config(self):
        result = self.match(name="Самописная")
        self.assertIsNone(result["направление"])
        self.assertIn("ka", result["причина"])
        self.assertIn("ut", result["причина"])
        self.assertNotIn("unf", result["причина"])

    def test_empty_is_error(self):
        self.assertIn("ошибка", self.match())
        self.assertIn("ошибка", self.match(name="  "))


class Pack(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tree = kf.fixture_copy(cls)
        cls.snap = kf.snapshot_of(cls.tree, revision="abc123")

    def pack(self, **args):
        return instructions.tool_get_instructions(self.snap, args)

    def test_plain_track(self):
        result = self.pack(track="ut")
        self.assertEqual("ut", result["направление"])
        self.assertEqual("abc123", result["ревизия"])
        self.assertEqual([], result["расширяет"])
        self.assertEqual(["where_is.md", "objects.md", "notes.md", "faq.md"],
                         [part["имя"] for part in result["части"]])
        self.assertEqual({"ut"}, {part["направление"] for part in result["части"]})
        self.assertEqual(["ut-orders", "ut-stock"], [chip["id"] for chip in result["чипы"]])
        self.assertIn("## Где это в 1С\n", result["текст"])
        self.assertIn("Заказы клиентов", result["текст"])
        self.assertNotIn("шпаргалки", result)
        self.assertNotIn("Шпаргалки", result["текст"])
        self.assertEqual("ut", result["профиль"]["семейство"])
        self.assertEqual(len(result["текст"].encode("utf-8")), result["размер"])

    def test_extends_puts_base_first_then_own(self):
        result = self.pack(track="ka")
        self.assertEqual(["ut"], result["расширяет"])
        order = [(part["направление"], part["имя"]) for part in result["части"]]
        self.assertEqual([("ut", "where_is.md"), ("ut", "objects.md"), ("ut", "notes.md"),
                          ("ut", "faq.md"), ("ka", "where_is.md"), ("ka", "notes.md")], order)
        self.assertEqual(["ut-orders", "ut-stock", "ka-osv"], [chip["id"] for chip in result["чипы"]])
        self.assertEqual("ka", result["чипы"][-1]["направление"])
        text = result["текст"]
        self.assertIn("## Где это в 1С (общее, ut)", text)
        self.assertIn("## Где это в 1С (добавки ka)", text)
        self.assertLess(text.index("(общее, ut)"), text.index("(добавки ka)"))
        self.assertEqual("Хозрасчетный", result["профиль"]["план_счетов"])

    def test_include_core_appends_cheats(self):
        result = self.pack(track="ut", include_core=True)
        self.assertEqual(["accounting", "queries"], [cheat["имя"] for cheat in result["шпаргалки"]])
        self.assertIn("# Шпаргалки платформы", result["текст"])
        self.assertIn("## Язык запросов", result["текст"])
        self.assertLess(result["текст"].index("Типовые вопросы"), result["текст"].index("Шпаргалки"))

    def test_track_without_pack_or_unknown(self):
        for track in ("unf", "core", "нет", ""):
            result = self.pack(track=track)
            self.assertIn("ошибка", result, track)
            self.assertIn("ka", result["ошибка"])

    def test_cheats_tool(self):
        result = instructions.tool_get_cheats(self.snap, {})
        self.assertEqual("core", result["направление"])
        self.assertEqual(["accounting", "queries"], [c["имя"] for c in result["шпаргалки"]])
        self.assertEqual("Регистр бухгалтерии", result["шпаргалки"][0]["заголовок"])
        self.assertIn("%ПланСчетов%", result["текст"])
        self.assertIn("ошибка", instructions.tool_get_cheats(self.snap, {"track": "ut"}))

    def test_tools_list_and_handlers_via_server(self):
        tools, handlers = server.enabled_tools(self.snap, {"instructions"})
        names = [tool["name"] for tool in tools]
        self.assertEqual(12, len(names))
        self.assertEqual(["match_config", "get_instructions", "get_cheats"], names[-3:])
        for tool in tools[-3:]:
            self.assertTrue(tool["annotations"]["readOnlyHint"], tool["name"])
        answer = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": "get_instructions", "arguments": {"track": "ka"}}},
                               self.snap, tools, handlers)
        self.assertNotIn("isError", answer)
        self.assertEqual("ka", json.loads(answer["content"][0]["text"])["направление"])
        init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2025-11-25"}}, self.snap, tools, handlers)
        self.assertEqual("2025-11-25", init["protocolVersion"])
        self.assertIn("get_instructions", init["instructions"])
        self.assertEqual(self.snap.digest, init["serverInfo"]["version"])
        plain = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": "2099-01-01"}}, self.snap)
        self.assertEqual(server.PROTOCOL, plain["protocolVersion"])
        self.assertNotIn("get_instructions", plain["instructions"])


if __name__ == "__main__":
    unittest.main()
