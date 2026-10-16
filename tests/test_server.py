# -*- coding: utf-8 -*-
"""MCP-сервер: без флага — 9 инструментов правил и рецептов, с --tools offline — ещё where_is."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "mcp", "server.py")
FIXTURE = os.path.join(ROOT, "fixtures", "dump-mini")


def call(requests, args=(), env=None):
    environ = dict(os.environ)
    environ.pop("TINY1C_TOOLS", None)
    environ.update(env or {})
    payload = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in requests)
    done = subprocess.run([sys.executable, SERVER] + list(args), input=payload.encode("utf-8"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environ,
                          cwd=ROOT, timeout=60, check=True)
    return [json.loads(line) for line in done.stdout.decode("utf-8").splitlines() if line]


GUIDE_FIXTURE = os.path.join(ROOT, "tests", "fixtures", "guides", "how-901.md")


def guide_root(case):
    """Копия сервера с манифестом, в котором есть синтетический рецепт how-901.

    Реальные рецепты в наборе могут быть, а могут и не быть: проверка инструментов
    рецептов от них не зависит. Сервер берёт корень набора из своего расположения,
    поэтому копируется mcp/, а рядом кладутся manifest.json и файл рецепта.
    """
    tmp = tempfile.mkdtemp(prefix="tiny1c-guide-root-")
    case.addCleanup(shutil.rmtree, tmp, True)
    shutil.copytree(os.path.join(ROOT, "mcp"), os.path.join(tmp, "mcp"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    spec = importlib.util.spec_from_file_location("tiny1c_manifest_for_server_test",
                                                  os.path.join(ROOT, "scripts", "manifest.py"))
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    track_dir = os.path.join(tmp, "tracks", "core")
    os.makedirs(os.path.join(track_dir, "guides"))
    shutil.copy(GUIDE_FIXTURE, os.path.join(track_dir, "guides", "how-901.md"))
    errors = []
    guides = builder.collect_guides("core", track_dir, set(), errors)
    case.assertEqual([], errors)
    with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as handle:
        data = json.load(handle)
    data["рецептов"] = len(guides)
    data["рецепты"] = guides
    for track in data["направления"]:
        if track["код"] == "core":
            track["рецептов"] = len(guides)
            track["рецепты"] = [guide["id"] for guide in guides]
    with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return tmp


def call_in(root, requests, args=()):
    payload = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in requests)
    done = subprocess.run([sys.executable, os.path.join(root, "mcp", "server.py")] + list(args),
                          input=payload.encode("utf-8"), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, cwd=root, timeout=60, check=True)
    return [json.loads(line) for line in done.stdout.decode("utf-8").splitlines() if line]


def tool_names(args=(), env=None):
    answer = call([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}], args, env)[0]
    return [tool["name"] for tool in answer["result"]["tools"]]


def where_is(arguments, args=("--tools", "offline")):
    answer = call([{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "where_is", "arguments": arguments}}], args)[0]
    return answer


class ServerTools(unittest.TestCase):

    def test_default_is_nine_rule_and_guide_tools(self):
        names = tool_names()
        self.assertEqual(9, len(names))
        self.assertIn("lookup_guide", names)
        self.assertIn("get_guide", names)
        self.assertNotIn("where_is", names)

    def test_flag_adds_where_is(self):
        for args, env in ((("--tools", "offline"), None), (("--tools=offline",), None),
                          ((), {"TINY1C_TOOLS": "offline"})):
            names = tool_names(args, env)
            self.assertEqual(10, len(names), (args, env))
            self.assertEqual("where_is", names[-1])

    def test_checklist_knows_external_processors(self):
        # Внешние обработки и отчёты (.epf/.erf) - своя категория плюс общие для модулей, форм и макетов.
        for name in ("Печать.epf", "Отчет.ERF"):
            answer = call([{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                            "params": {"name": "checklist", "arguments": {"file": name}}}])[0]
            result = json.loads(answer["result"]["content"][0]["text"])
            self.assertEqual("дополнительные-отчеты-и-обработки", result["категории"][0], name)
            self.assertIn("макеты", result["категории"], name)

    def test_checklist_knows_extensions(self):
        # Расширения конфигурации: .cfe и файлы выгрузки Конфигуратора (.xml) тянут категорию «расширения».
        for name, first in (("Доработки.cfe", "расширения"), ("Configuration.xml", None)):
            answer = call([{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                            "params": {"name": "checklist", "arguments": {"file": name}}}])[0]
            result = json.loads(answer["result"]["content"][0]["text"])
            self.assertIn("расширения", result["категории"], name)
            if first:
                self.assertEqual(first, result["категории"][0], name)
            self.assertTrue(any(rule["id"].startswith("ext-") for rule in result["правила"]), name)

    def test_where_is_is_read_only(self):
        answer = call([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}],
                      ("--tools", "offline"))[0]
        tool = [item for item in answer["result"]["tools"] if item["name"] == "where_is"][0]
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        self.assertFalse(tool["annotations"]["destructiveHint"])

    def test_where_is_without_flag_is_unknown(self):
        answer = where_is({"dump": FIXTURE, "query": "акт"}, args=())
        self.assertIn("error", answer)

    def test_call_where_is(self):
        answer = where_is({"dump": FIXTURE, "query": "Документ.АктВыполненныхРабот"})
        result = json.loads(answer["result"]["content"][0]["text"])
        self.assertEqual(1, result["найдено"])
        self.assertEqual("e1cib/list/Документ.АктВыполненныхРабот",
                         result["объекты"][0]["навигационная_ссылка"])

    def test_call_where_is_rejects_bad_dump(self):
        answer = where_is({"dump": os.path.join(FIXTURE, ".."), "query": "акт"})
        result = json.loads(answer["result"]["content"][0]["text"])
        self.assertIn("Configuration.xml", result["ошибка"])

    def test_cp1251_locale_does_not_break_cyrillic(self):
        # Windows: pipe-кодировка процесса - cp1251. Сервер обязан читать и писать UTF-8 всё равно.
        request = [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "lookup_rule", "arguments": {"query": "шапка"}}}]
        counts = []
        for env in (None, {"PYTHONIOENCODING": "cp1251"}, {"PYTHONIOENCODING": "cp1251",
                                                           "PYTHONUTF8": "0"}):
            answer = call(request, env=env)[0]
            counts.append(json.loads(answer["result"]["content"][0]["text"]))
        self.assertGreaterEqual(counts[0]["найдено"], 2)
        self.assertEqual(counts[0], counts[1])
        self.assertEqual(counts[0], counts[2])

    def test_initialize_has_instructions_and_hash_version(self):
        answer = call([{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])[0]["result"]
        lines = answer["instructions"].splitlines()
        self.assertTrue(8 <= len(lines) <= 12, len(lines))
        self.assertIn("checklist", answer["instructions"])
        self.assertRegex(answer["serverInfo"]["version"], r"^[0-9a-f]{12}$")
        again = call([{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])[0]["result"]
        self.assertEqual(answer["serverInfo"]["version"], again["serverInfo"]["version"])

    def test_tool_errors_are_is_error_not_rpc_error(self):
        for name, arguments in (("lookup_rule", {"query": ""}), ("get_rule", {"id": "нет-999"}),
                                ("checklist", {"file": "a.unknown"})):
            answer = call([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments}}])[0]
            self.assertNotIn("error", answer, name)
            self.assertTrue(answer["result"]["isError"], name)
        ok = call([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                    "params": {"name": "get_rule", "arguments": {"id": "bsl-006"}}}])[0]
        self.assertNotIn("isError", ok["result"])

    def test_unknown_protocol_method_stays_rpc_error(self):
        answer = call([{"jsonrpc": "2.0", "id": 1, "method": "нет/такого"}])[0]
        self.assertIn("error", answer)

    def test_checklist_compact(self):
        def run(arguments):
            answer = call([{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": "checklist", "arguments": arguments}}])[0]
            return json.loads(answer["result"]["content"][0]["text"])
        full, compact = run({"file": "a.bsl"}), run({"file": "a.bsl", "compact": True})
        self.assertEqual(full["найдено"], compact["найдено"])
        self.assertEqual({"id", "заголовок", "серьёзность"}, set(compact["правила"][0]))
        self.assertIn("источник", full["правила"][0])
        self.assertEqual(full["правила"][0]["id"], compact["правила"][0]["id"])

    def test_lookup_guide_finds_first_batch(self):
        root = guide_root(self)
        for query in ("how-901", "условный артефакт", "загрузить артефакт активен", "how"):
            answer = call_in(root, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": "lookup_guide",
                                                "arguments": {"query": query}}}])[0]
            result = json.loads(answer["result"]["content"][0]["text"])
            self.assertEqual(["how-901"], [item["id"] for item in result["рецепты"]], query)
        card = result["рецепты"][0]
        self.assertEqual(["ext-002", "ext-004"], card["правила"])
        self.assertIn("задача", card)
        self.assertNotIn("текст", card)
        self.assertNotIn("серьёзность", card)
        # фильтры и ошибки
        for arguments, found in (({"query": "how", "category": "запросы"}, 0),
                                 ({"query": "how", "category": "расширения"}, 1),
                                 ({"query": "how", "track": "unf"}, 0),
                                 ({"query": "how", "platform": "8.5"}, 1)):
            answer = call_in(root, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": "lookup_guide",
                                                "arguments": arguments}}])[0]
            self.assertEqual(found, json.loads(answer["result"]["content"][0]["text"])["найдено"],
                             arguments)
        answer = call_in(root, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": "lookup_guide",
                                            "arguments": {"query": " "}}}])[0]
        self.assertTrue(answer["result"]["isError"])

    def test_lookup_rule_does_not_see_guides_and_back(self):
        root = guide_root(self)
        answer = call_in(root, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": "lookup_rule",
                                            "arguments": {"query": "how-901"}}},
                                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                 "params": {"name": "lookup_guide",
                                            "arguments": {"query": "how-901"}}},
                                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                 "params": {"name": "lookup_rule",
                                            "arguments": {"query": "шапка"}}}])
        self.assertEqual(0, json.loads(answer[0]["result"]["content"][0]["text"])["найдено"])
        self.assertEqual(1, json.loads(answer[1]["result"]["content"][0]["text"])["найдено"])
        # кэши индексов не сбрасывают друг друга: после рецептов правила находятся по-прежнему
        self.assertGreaterEqual(json.loads(answer[2]["result"]["content"][0]["text"])["найдено"], 2)

    def test_get_guide_returns_body_and_rules(self):
        root = guide_root(self)
        answer = call_in(root, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": "get_guide",
                                            "arguments": {"id": "how-901"}}}])[0]
        self.assertNotIn("isError", answer["result"])
        result = json.loads(answer["result"]["content"][0]["text"])
        self.assertEqual(["ext-002", "ext-004"], result["правила"])
        self.assertIn("## Шаги", result["текст"])
        self.assertEqual("tracks/core/guides/how-901.md", result["файл"])
        missing = call_in(root, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "get_guide",
                                             "arguments": {"id": "how-999"}}}])[0]
        self.assertTrue(missing["result"]["isError"])

    def test_list_tracks_counts_guides(self):
        root = guide_root(self)
        answer = call_in(root, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": "list_tracks", "arguments": {}}}])[0]
        tracks = json.loads(answer["result"]["content"][0]["text"])
        self.assertEqual(1, [track for track in tracks if track["код"] == "core"][0]["рецептов"])

    def test_guides_in_initialize_and_resource(self):
        root = guide_root(self)
        answer = call_in(root, [{"jsonrpc": "2.0", "id": 1, "method": "initialize"}])[0]["result"]
        lines = answer["instructions"].splitlines()
        self.assertTrue(8 <= len(lines) <= 12, len(lines))
        self.assertIn("lookup_guide", answer["instructions"])
        self.assertIn("рецептов 1", answer["instructions"])
        resource = call_in(root, [{"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                                   "params": {"uri": "tiny1c://manifest"}}])[0]
        text = resource["result"]["contents"][0]["text"]
        self.assertIn("рецепты", text)
        self.assertIn("how-901", text)
        self.assertLess(len(text), 60000)
        self.assertNotIn("симптом", text)
        self.assertNotIn("глоссарий", text)

    def test_manifest_resource_is_short(self):
        answer = call([{"jsonrpc": "2.0", "id": 1, "method": "resources/read",
                        "params": {"uri": "tiny1c://manifest"}}])[0]
        text = answer["result"]["contents"][0]["text"]
        self.assertLess(len(text), 60000)
        self.assertNotIn("симптом", text)
        self.assertNotIn("глоссарий", text)


if __name__ == "__main__":
    unittest.main()
