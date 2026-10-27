#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сетевой режим tiny1C: MCP поверх streamable HTTP для сервисов во внутренней сети.

Тот же набор инструментов и тот же handle(), что у stdio-сервера (mcp/server.py),
плюс:

  * один MCP-эндпоинт `POST /mcp` по спецификации MCP (streamable HTTP, ревизии
    2024-11-05…2025-11-25): JSON-RPC запрос или батч в теле; ответ — один JSON
    (или SSE с одним событием, если клиент принимает только text/event-stream);
    уведомление — 202 без тела; сессий нет (Mcp-Session-Id не выдаётся и не
    требуется); заголовок MCP-Protocol-Version без значения = 2025-03-26,
    неизвестное значение — 400; GET и DELETE на /mcp — 405;
  * доступ только по сервис-токену: заголовок X-Service-Token должен совпасть с
    TINY1C_SERVICE_TOKEN; без токена в окружении сервис не стартует. Запрос с
    заголовком Origin (браузер) — 403: сервис не для браузеров;
  * `GET /healthz` без токена: ревизия знаний, время и итог последней
    синхронизации — для healthcheck контейнера и панели портала;
  * знания подгружаются из git сами (mcp/knowledge.py), код — нет.

Запуск:
  TINY1C_SERVICE_TOKEN=... mcp/httpd.py [--addr 0.0.0.0:8111] [--data /data]
      [--repo URL] [--branch main] [--interval 300] [--tools instructions[,offline]]
      [--once]   # одна синхронизация и выход (проверка доступа к репозиторию)
Переменные окружения: TINY1C_HTTP_ADDR, TINY1C_DATA, TINY1C_REPO_URL, TINY1C_BRANCH,
TINY1C_SYNC_INTERVAL, TINY1C_TOOLS (по умолчанию instructions).
"""

import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import knowledge as kn  # noqa: E402
import server  # noqa: E402

MAX_BODY = 256 * 1024
MAX_BATCH = 20
TOKEN_HEADER = "X-Service-Token"
ASSUMED_PROTOCOL = "2025-03-26"   # запрос без MCP-Protocol-Version (клиенты до 2025-06-18)
DEFAULT_ADDR = "0.0.0.0:8111"
DEFAULT_INTERVAL = 300
DEFAULT_GROUPS = "instructions"


class App:
    """Состояние сервиса: знания, токен, группы инструментов, кэш tools/handlers по снимку."""

    def __init__(self, knowledge, token, groups=("instructions",)):
        self.knowledge = knowledge
        self.token = token
        self.groups = set(groups)
        self._cache = {}
        self.started = time.time()

    def tools_for(self, manifest):
        key = id(manifest)
        cached = self._cache.get(key)
        if cached is None or cached[0] is not manifest:
            self._cache = {key: (manifest,) + server.enabled_tools(manifest, self.groups)}
            cached = self._cache[key]
        return cached[1], cached[2]

    def token_ok(self, given):
        return bool(given) and hmac.compare_digest(given.encode("utf-8"), self.token.encode("utf-8"))

    def dispatch(self, request, manifest):
        """Один запрос JSON-RPC -> ответ (или None для уведомления)."""
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" \
                or not isinstance(request.get("method"), str):
            return {"jsonrpc": "2.0", "id": None if not isinstance(request, dict) else request.get("id"),
                    "error": {"code": -32600, "message": "не запрос JSON-RPC 2.0"}}
        request_id = request.get("id")
        tools, handlers = self.tools_for(manifest)
        try:
            result = server.handle(request, manifest, tools, handlers)
        except Exception as error:  # ошибка протокола -> JSON-RPC error
            if request_id is None:
                return None
            return {"jsonrpc": "2.0", "id": request_id,
                    "error": {"code": getattr(error, "code", -32603), "message": str(error)}}
        if request_id is None or result is None:
            return None
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


class Handler(BaseHTTPRequestHandler):
    server_version = "tiny1c-mcp"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    @property
    def app(self):
        return self.server.app

    def log_message(self, fmt, *args):
        if getattr(self.server, "log_requests", True):
            sys.stderr.write("%s %s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S"),
                                             self.address_string(), fmt % args))

    # --- ответы ---------------------------------------------------------------

    def send_json(self, status, payload, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if status >= 400:
            self.refuse()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def send_empty(self, status, headers=None):
        if status >= 400:
            self.refuse()
        self.send_response(status)
        self.send_header("Content-Length", "0")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()

    def refuse(self):
        """Отказ до чтения тела: соединение закрывается, иначе остаток тела прочтётся как следующий запрос."""
        self.close_connection = True

    def rpc_error(self, status, code, message, request_id=None):
        self.send_json(status, {"jsonrpc": "2.0", "id": request_id,
                                "error": {"code": code, "message": message}})

    # --- маршруты ------------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            status = self.app.knowledge.status()
            status["ок"] = status["ревизия"] is not None
            status["аптайм_с"] = int(time.time() - self.app.started)
            self.send_json(200 if status["ок"] else 503, status)
        elif path == "/mcp":
            self.send_empty(405, {"Allow": "POST"})  # SSE-поток сервер не открывает
        else:
            self.send_empty(404)

    def do_DELETE(self):
        self.send_empty(405, {"Allow": "POST"})  # сессий нет — нечего завершать

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/mcp":
            self.send_empty(404)
            return
        if not self.app.token_ok(self.headers.get(TOKEN_HEADER, "")):
            self.rpc_error(401, -32001, "нужен заголовок %s" % TOKEN_HEADER)
            return
        if self.headers.get("Origin"):
            self.rpc_error(403, -32001, "сервис не принимает запросы браузера (Origin)")
            return
        version = self.headers.get("MCP-Protocol-Version", "").strip() or ASSUMED_PROTOCOL
        if version not in server.KNOWN_PROTOCOLS:
            self.rpc_error(400, -32600, "версия протокола %s не поддерживается, есть: %s"
                           % (version, ", ".join(server.KNOWN_PROTOCOLS)))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self.rpc_error(413 if length > MAX_BODY else 411, -32600,
                           "тело запроса до %d байт" % MAX_BODY)
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self.rpc_error(400, -32700, "тело не JSON")
            return
        batch = isinstance(payload, list)
        requests = payload if batch else [payload]
        if batch and (not requests or len(requests) > MAX_BATCH):
            self.rpc_error(400, -32600, "батч от 1 до %d запросов" % MAX_BATCH)
            return

        manifest = self.app.knowledge.current  # один снимок на весь запрос
        responses = [item for item in (self.app.dispatch(request, manifest) for request in requests)
                     if item is not None]
        if not responses:
            self.send_empty(202)
            return
        body = responses if batch else responses[0]
        accept = self.headers.get("Accept", "")
        if "text/event-stream" in accept and "application/json" not in accept and "*/*" not in accept:
            self.send_sse(body)
        else:
            self.send_json(200, body)

    def send_sse(self, body):
        data = json.dumps(body, ensure_ascii=False)
        chunk = ("event: message\ndata: %s\n\n" % data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(chunk)))
        self.end_headers()
        self.wfile.write(chunk)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr, app, log_requests=True):
        super().__init__(addr, Handler)
        self.app = app
        self.log_requests = log_requests


def parse_addr(text):
    host, _, port = text.rpartition(":")
    return host or "0.0.0.0", int(port)


def option(argv, environ, name, env_name, default=None):
    value = environ.get(env_name, default)
    for position, arg in enumerate(argv):
        if arg == name and position + 1 < len(argv):
            value = argv[position + 1]
        elif arg.startswith(name + "="):
            value = arg.split("=", 1)[1]
    return value


def build(argv, environ):
    """App + адрес + интервал из аргументов и окружения; SystemExit без токена."""
    token = environ.get("TINY1C_SERVICE_TOKEN", "").strip()
    if not token:
        raise SystemExit("tiny1c: нет TINY1C_SERVICE_TOKEN — сетевой режим без токена не стартует")
    groups = {item.strip() for item in
              str(option(argv, environ, "--tools", "TINY1C_TOOLS", DEFAULT_GROUPS)).split(",")
              if item.strip()}
    unknown = groups - set(server.GROUPS)
    if unknown:
        raise SystemExit("tiny1c: неизвестная группа инструментов: %s (есть: %s)"
                         % (", ".join(sorted(unknown)), ", ".join(server.GROUPS)))
    knowledge = kn.Knowledge(
        data_dir=option(argv, environ, "--data", "TINY1C_DATA") or None,
        repo_url=option(argv, environ, "--repo", "TINY1C_REPO_URL", kn.DEFAULT_REPO),
        branch=option(argv, environ, "--branch", "TINY1C_BRANCH", kn.DEFAULT_BRANCH),
    )
    addr = parse_addr(option(argv, environ, "--addr", "TINY1C_HTTP_ADDR", DEFAULT_ADDR))
    interval = int(option(argv, environ, "--interval", "TINY1C_SYNC_INTERVAL", DEFAULT_INTERVAL))
    return App(knowledge, token, groups), addr, interval


def main(argv=None, environ=None):
    argv = sys.argv[1:] if argv is None else argv
    environ = os.environ if environ is None else environ
    app, addr, interval = build(argv, environ)
    app.knowledge.start()
    if "--once" in argv:
        changed = app.knowledge.sync_once()
        status = app.knowledge.status()["последняя_синхронизация"]
        print(json.dumps({"изменилось": changed, **status}, ensure_ascii=False))
        return 0 if status["ок"] else 1
    stop = threading.Event()
    if app.knowledge.data_dir:
        threading.Thread(target=app.knowledge.run, args=(interval, stop), daemon=True,
                         name="tiny1c-sync").start()
    httpd = Server(addr, app)
    sys.stderr.write("tiny1c: MCP по HTTP на %s:%d, инструменты: %s, знания: %s\n"
                     % (addr[0], addr[1], ", ".join(sorted(app.groups)) or "базовые",
                        "git %s каждые %d с" % (app.knowledge.repo_url, interval)
                        if app.knowledge.data_dir else "только встроенная копия"))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
