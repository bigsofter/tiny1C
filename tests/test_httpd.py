# -*- coding: utf-8 -*-
"""Сетевой режим mcp/httpd.py: токен, /healthz, транспорт streamable HTTP, горячая подмена снимка."""

import http.client
import json
import threading
import unittest

from tests import knowledge_fixture as kf

httpd = kf.load_module("tiny1c_httpd", "mcp", "httpd.py")
knowledge = kf.load_module("tiny1c_knowledge_for_httpd", "mcp", "knowledge.py")

TOKEN = "test-token-7f3a"


class HttpServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tree = kf.fixture_copy(cls)
        cls.knowledge = knowledge.Knowledge(image_root=cls.tree)
        cls.knowledge.start()
        cls.app = httpd.App(cls.knowledge, TOKEN, {"instructions"})
        cls.server = httpd.Server(("127.0.0.1", 0), cls.app, log_requests=False)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, method, path, body=None, headers=None, token=TOKEN, version="2025-11-25"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        base = {"Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"}
        if token is not None:
            base["X-Service-Token"] = token
        if version is not None:
            base["MCP-Protocol-Version"] = version
        base.update(headers or {})
        data = None if body is None else (body if isinstance(body, bytes)
                                           else json.dumps(body, ensure_ascii=False).encode("utf-8"))
        conn.request(method, path, body=data, headers=base)
        response = conn.getresponse()
        raw = response.read()
        conn.close()
        return response.status, dict(response.getheaders()), raw

    def rpc(self, method, params=None, request_id=1, **extra):
        payload = {"jsonrpc": "2.0", "method": method}
        if request_id is not None:
            payload["id"] = request_id
        if params is not None:
            payload["params"] = params
        return self.request("POST", "/mcp", payload, **extra)

    @staticmethod
    def tool_text(raw):
        return json.loads(json.loads(raw)["result"]["content"][0]["text"])

    # --- доступ ---------------------------------------------------------------

    def test_token_required(self):
        for token in (None, "", "other"):
            status, _, raw = self.rpc("tools/list", token=token)
            self.assertEqual(401, status, token)
            self.assertEqual(-32001, json.loads(raw)["error"]["code"])

    def test_origin_is_refused(self):
        status, _, _ = self.rpc("tools/list", headers={"Origin": "https://example.invalid"})
        self.assertEqual(403, status)

    def test_healthz_is_open(self):
        status, _, raw = self.request("GET", "/healthz", token=None)
        self.assertEqual(200, status)
        body = json.loads(raw)
        self.assertTrue(body["ок"])
        self.assertEqual("встроенная", body["ревизия"])
        self.assertEqual("образ", body["источник"])
        self.assertEqual(2, body["инструкций"])
        self.assertIsNone(body["репозиторий"])

    def test_other_paths_and_methods(self):
        self.assertEqual(404, self.request("GET", "/", token=None)[0])
        status, headers, _ = self.request("GET", "/mcp")
        self.assertEqual(405, status)
        self.assertEqual("POST", headers.get("Allow"))
        self.assertEqual(405, self.request("DELETE", "/mcp")[0])
        self.assertEqual(404, self.request("POST", "/other", {"jsonrpc": "2.0", "id": 1, "method": "ping"})[0])

    # --- протокол -------------------------------------------------------------

    def test_initialize_negotiates_version_and_no_session(self):
        status, headers, raw = self.rpc("initialize", {"protocolVersion": "2025-11-25",
                                                       "capabilities": {},
                                                       "clientInfo": {"name": "t", "version": "1"}})
        self.assertEqual(200, status)
        self.assertNotIn("Mcp-Session-Id", headers)
        result = json.loads(raw)["result"]
        self.assertEqual("2025-11-25", result["protocolVersion"])
        self.assertEqual("tiny1c", result["serverInfo"]["name"])
        self.assertEqual(self.knowledge.current.digest, result["serverInfo"]["version"])
        self.assertIn("get_instructions", result["instructions"])

    def test_protocol_header_optional_but_must_be_known(self):
        self.assertEqual(200, self.rpc("ping", version=None)[0])
        self.assertEqual(200, self.rpc("ping", version="2024-11-05")[0])
        status, _, raw = self.rpc("ping", version="2099-01-01")
        self.assertEqual(400, status)
        self.assertIn("2025-11-25", json.loads(raw)["error"]["message"])

    def test_tools_list_has_instructions_group(self):
        status, headers, raw = self.rpc("tools/list")
        self.assertEqual(200, status)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        names = [tool["name"] for tool in json.loads(raw)["result"]["tools"]]
        self.assertEqual(13, len(names))
        self.assertIn("match_config", names)
        self.assertIn("get_instructions_file", names)
        self.assertIn("get_instructions", names)
        self.assertIn("get_cheats", names)
        self.assertNotIn("where_is", names)  # у фикстуры нет карточки инструмента

    def test_notification_is_202_without_body(self):
        status, _, raw = self.rpc("notifications/initialized", request_id=None)
        self.assertEqual(202, status)
        self.assertEqual(b"", raw)

    def test_batch(self):
        payload = [{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                   {"jsonrpc": "2.0", "method": "notifications/initialized"},
                   {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "match_config", "arguments": {"name": "УправлениеТорговлей"}}}]
        status, _, raw = self.request("POST", "/mcp", payload)
        self.assertEqual(200, status)
        answers = json.loads(raw)
        self.assertEqual([1, 2], [item["id"] for item in answers])
        self.assertEqual("ut", json.loads(answers[1]["result"]["content"][0]["text"])["направление"])
        self.assertEqual(400, self.request("POST", "/mcp", [])[0])

    def test_sse_only_when_client_accepts_only_events(self):
        status, headers, raw = self.rpc("ping", headers={"Accept": "text/event-stream"})
        self.assertEqual(200, status)
        self.assertTrue(headers["Content-Type"].startswith("text/event-stream"))
        self.assertTrue(raw.startswith(b"event: message\ndata: "))
        self.assertEqual({}, json.loads(raw.split(b"data: ", 1)[1].split(b"\n", 1)[0])["result"])
        status, headers, _ = self.rpc("ping", headers={"Accept": "application/json, text/event-stream"})
        self.assertTrue(headers["Content-Type"].startswith("application/json"))

    def test_unknown_method_and_tool_are_rpc_errors_not_http_errors(self):
        status, _, raw = self.rpc("server/discover")
        self.assertEqual(200, status)
        self.assertEqual(-32601, json.loads(raw)["error"]["code"])
        status, _, raw = self.rpc("tools/call", {"name": "нет", "arguments": {}})
        self.assertEqual(200, status)
        self.assertEqual(-32602, json.loads(raw)["error"]["code"])
        status, _, raw = self.rpc("tools/call", {"name": "get_instructions", "arguments": {"track": "unf"}})
        self.assertEqual(200, status)
        self.assertTrue(json.loads(raw)["result"]["isError"])

    def test_bad_bodies(self):
        status, _, raw = self.request("POST", "/mcp", "{не json".encode("utf-8"))
        self.assertEqual(400, status)
        self.assertEqual(-32700, json.loads(raw)["error"]["code"])
        status, _, raw = self.request("POST", "/mcp", {"jsonrpc": "1.0", "id": 1, "method": "ping"})
        self.assertEqual(200, status)
        self.assertEqual(-32600, json.loads(raw)["error"]["code"])
        status, _, _ = self.request("POST", "/mcp", b"x" * (httpd.MAX_BODY + 1))
        self.assertEqual(413, status)

    # --- инструменты Татьяны по HTTP -----------------------------------------

    def test_get_instructions_over_http(self):
        status, _, raw = self.rpc("tools/call", {"name": "get_instructions",
                                                 "arguments": {"track": "ka", "include_core": True}})
        self.assertEqual(200, status)
        result = self.tool_text(raw)
        self.assertEqual("ka", result["направление"])
        self.assertEqual(["ut"], result["расширяет"])
        self.assertEqual("встроенная", result["ревизия"])
        self.assertIn("Регламентированный учёт", result["текст"])
        self.assertIn("Заказы клиентов", result["текст"])
        self.assertIn("Язык запросов", result["текст"])

    def test_hot_swap_of_snapshot_changes_answers(self):
        other_tree = kf.fixture_copy(self)
        with open(f"{other_tree}/tracks/ut/where_is.md", "a", encoding="utf-8") as handle:
            handle.write("| Новая особенность после обновления знаний | Продажи | Продажи → Новое |\n")
        builder = kf.load_module("tiny1c_manifest_hot", "scripts", "manifest.py")
        manifest, errors = builder.collect(root=other_tree)
        self.assertEqual([], errors)
        import snapshot
        new = snapshot.load(other_tree, revision="deadbeef1234", manifest_text=builder.render(manifest))
        old = self.knowledge.current
        self.knowledge.current = new
        try:
            result = self.tool_text(self.rpc("tools/call", {"name": "get_instructions",
                                                            "arguments": {"track": "ut"}})[2])
            self.assertEqual("deadbeef1234", result["ревизия"])
            self.assertIn("Новая особенность", result["текст"])
            names = [t["name"] for t in json.loads(self.rpc("tools/list")[2])["result"]["tools"]]
            self.assertEqual(13, len(names))
        finally:
            self.knowledge.current = old
        result = self.tool_text(self.rpc("tools/call", {"name": "get_instructions",
                                                        "arguments": {"track": "ut"}})[2])
        self.assertEqual("встроенная", result["ревизия"])
        self.assertNotIn("Новая особенность", result["текст"])


class Build(unittest.TestCase):

    def test_token_is_mandatory(self):
        with self.assertRaises(SystemExit):
            httpd.build([], {})
        with self.assertRaises(SystemExit):
            httpd.build([], {"TINY1C_SERVICE_TOKEN": "  "})

    def test_options_from_env_and_argv(self):
        app, addr, interval = httpd.build(["--addr", "127.0.0.1:9", "--tools", "instructions,offline"],
                                          {"TINY1C_SERVICE_TOKEN": "t", "TINY1C_SYNC_INTERVAL": "7",
                                           "TINY1C_DATA": "", "TINY1C_REPO_URL": "https://example.invalid/r"})
        self.assertEqual(("127.0.0.1", 9), addr)
        self.assertEqual(7, interval)
        self.assertEqual({"instructions", "offline"}, app.groups)
        self.assertIsNone(app.knowledge.data_dir)
        self.assertEqual("https://example.invalid/r", app.knowledge.repo_url)
        with self.assertRaises(SystemExit):
            httpd.build(["--tools", "online"], {"TINY1C_SERVICE_TOKEN": "t"})


if __name__ == "__main__":
    unittest.main()
