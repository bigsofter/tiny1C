# -*- coding: utf-8 -*-
"""MCP-сервер: без флага — 7 инструментов правил, с --tools offline — ещё where_is."""

import json
import os
import subprocess
import sys
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


def tool_names(args=(), env=None):
    answer = call([{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}], args, env)[0]
    return [tool["name"] for tool in answer["result"]["tools"]]


def where_is(arguments, args=("--tools", "offline")):
    answer = call([{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "where_is", "arguments": arguments}}], args)[0]
    return answer


class ServerTools(unittest.TestCase):

    def test_default_is_seven_rule_tools(self):
        names = tool_names()
        self.assertEqual(7, len(names))
        self.assertNotIn("where_is", names)

    def test_flag_adds_where_is(self):
        for args, env in ((("--tools", "offline"), None), (("--tools=offline",), None),
                          ((), {"TINY1C_TOOLS": "offline"})):
            names = tool_names(args, env)
            self.assertEqual(8, len(names), (args, env))
            self.assertEqual("where_is", names[-1])

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


if __name__ == "__main__":
    unittest.main()
