#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP-сервер tiny1C: правила разработки 1С, глоссарии и карты объектов.

Транспорт — stdio, JSON-RPC 2.0, без внешних зависимостей: сервер запускается
любым Python 3.8+ и ничего не требует ставить. Данные берутся из manifest.json,
который собирает scripts/manifest.py; тела правил читаются с диска по запросу.

Запуск вручную (для отладки):
  echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | mcp/server.py

Подключение в Claude Code (.mcp.json проекта):
  {"mcpServers": {"tiny1c": {"command": "python3",
                             "args": ["<путь>/tiny1C/mcp/server.py"]}}}
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "manifest.json")
PROTOCOL = "2024-11-05"

# По какому файлу какие категории правил применимы.
FILE_CATEGORIES = {
    ".bsl": ["модули", "запросы", "процесс"],
    ".form": ["формы-xml", "интерфейс", "процесс"],
    ".mdo": ["метаданные", "архитектура", "процесс"],
    ".mxlx": ["макеты", "процесс"],
    ".xml": ["формы-xml", "метаданные", "процесс"],
    ".dcs": ["запросы", "данные"],
}

TOOLS = [
    {
        "name": "list_tracks",
        "description": "Направления набора: ядро, разработка с нуля, типовые конфигурации "
                       "(УНФ, Бухгалтерия, ЗУП, ERP). Показывает статус, число правил и "
                       "терминов. Вызывать первым, когда неизвестно, какое направление брать.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "lookup_rule",
        "description": "Поиск правил по симптому, ключевому слову или id. Ищет по ключам, "
                       "заголовку и id. Возвращает карточки без тела — тело брать get_rule.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "симптом, текст ошибки, термин"},
                "track": {"type": "string", "description": "код направления, например unf"},
                "platform": {"type": "string", "description": "8.3 или 8.5"},
                "severity": {"type": "string", "description": "критично | важно | справка"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_rule",
        "description": "Полный текст правила по id со всеми полями: чем ловится (check), "
                       "откуда взято (источник), к каким объектам привязано.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    {
        "name": "rules_by_category",
        "description": "Все правила категории: запросы, модули, формы-xml, метаданные, "
                       "макеты, процесс, архитектура, интерфейс, данные, интеграция.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string"},
                "track": {"type": "string"},
            },
            "required": ["category"],
        },
    },
    {
        "name": "rules_for_object",
        "description": "Правила и термины, привязанные к объекту метаданных "
                       "(например «Документ.РасходнаяНакладная»). Сопоставление объектов "
                       "и правил внутри направления конфигурации.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "object": {"type": "string"},
                "track": {"type": "string"},
            },
            "required": ["object"],
        },
    },
    {
        "name": "checklist",
        "description": "Чек-лист перед правкой файла: применимые правила по его типу "
                       "(.bsl, .form, .mdo, .mxlx), по умолчанию только критичные и важные. "
                       "Вызывать ПЕРЕД правкой, а не после.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "имя или путь файла"},
                "track": {"type": "string"},
                "severity": {"type": "string", "description": "минимальная: критично | важно | справка"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "glossary_lookup",
        "description": "Термин предметной области или платформы: определение, синонимы и "
                       "объекты метаданных, которыми он выражен.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "term": {"type": "string"},
                "track": {"type": "string"},
            },
            "required": ["term"],
        },
    },
]

SEVERITY_ORDER = {"критично": 0, "важно": 1, "справка": 2}


def load_manifest():
    with open(MANIFEST, encoding="utf-8") as handle:
        return json.load(handle)


def rule_card(rule):
    return {
        "id": rule["id"],
        "направление": rule["направление"],
        "категория": rule["категория"],
        "серьёзность": rule["серьёзность"],
        "платформы": rule.get("платформы", []),
        "заголовок": rule["заголовок"],
        "чем_ловится": rule.get("check", []),
        "источник": rule.get("источник", ""),
    }


def matches(rule, track=None, platform=None, severity=None):
    if track and rule["направление"] != track:
        return False
    if platform and platform not in rule.get("платформы", []):
        return False
    if severity and SEVERITY_ORDER.get(rule["серьёзность"], 9) > SEVERITY_ORDER.get(severity, 9):
        return False
    return True


def tool_list_tracks(manifest, _args):
    return [{
        "код": track["код"],
        "название": track["название"],
        "вид": track["вид"],
        "статус": track["статус"],
        "конфигурации": track.get("конфигурации", []),
        "платформы": track.get("платформы", []),
        "правил": track["правил"],
        "терминов": track["терминов"],
        "карта_объектов": track.get("карта_объектов"),
    } for track in manifest["направления"]]


def tool_lookup_rule(manifest, args):
    query = args.get("query", "").strip().lower()
    found = []
    for rule in manifest["правила"]:
        if not matches(rule, args.get("track"), args.get("platform"), args.get("severity")):
            continue
        haystack = " ".join([rule["id"], rule["заголовок"]] + list(rule.get("ключи", []))).lower()
        if query and query not in haystack:
            continue
        found.append(rule_card(rule))
    found.sort(key=lambda card: SEVERITY_ORDER.get(card["серьёзность"], 9))
    return {"найдено": len(found), "правила": found}


def tool_get_rule(manifest, args):
    rule_id = args.get("id", "")
    for rule in manifest["правила"]:
        if rule["id"] == rule_id:
            path = os.path.join(ROOT, rule["файл"])
            with open(path, encoding="utf-8") as handle:
                body = handle.read()
            card = rule_card(rule)
            card["объекты"] = rule.get("объекты", [])
            card["файл"] = rule["файл"]
            card["текст"] = body
            return card
    return {"ошибка": "правила с id «%s» нет" % rule_id}


def tool_rules_by_category(manifest, args):
    category = args.get("category", "")
    found = [rule_card(rule) for rule in manifest["правила"]
             if rule["категория"] == category and matches(rule, args.get("track"))]
    found.sort(key=lambda card: SEVERITY_ORDER.get(card["серьёзность"], 9))
    return {"категория": category, "найдено": len(found), "правила": found}


def tool_rules_for_object(manifest, args):
    obj = args.get("object", "").strip()
    track = args.get("track")
    ids = manifest["объекты"].get(obj, [])
    rules = [rule_card(rule) for rule in manifest["правила"]
             if rule["id"] in ids and matches(rule, track)]
    terms = []
    for entry in manifest["направления"]:
        if track and entry["код"] != track:
            continue
        for term in entry["глоссарий"]:
            if obj in term["объекты"]:
                terms.append({"направление": entry["код"], **term})
    return {"объект": obj, "правила": rules, "термины": terms}


def tool_checklist(manifest, args):
    name = args.get("file", "")
    lowered = name.lower()
    extension = None
    if lowered.endswith("form.form") or lowered.endswith(".form"):
        extension = ".form"
    else:
        for candidate in FILE_CATEGORIES:
            if lowered.endswith(candidate):
                extension = candidate
                break
    if extension is None:
        return {"ошибка": "не знаю такой тип файла: %s" % name,
                "известные": sorted(FILE_CATEGORIES)}
    severity = args.get("severity", "важно")
    categories = FILE_CATEGORIES[extension]
    found = [rule_card(rule) for rule in manifest["правила"]
             if rule["категория"] in categories
             and matches(rule, args.get("track"), None, severity)]
    found.sort(key=lambda card: (SEVERITY_ORDER.get(card["серьёзность"], 9), card["id"]))
    return {"файл": name, "тип": extension, "категории": categories,
            "найдено": len(found), "правила": found}


def tool_glossary_lookup(manifest, args):
    query = args.get("term", "").strip().lower()
    track = args.get("track")
    found = []
    for entry in manifest["направления"]:
        if track and entry["код"] != track:
            continue
        for term in entry["глоссарий"]:
            haystack = " ".join([term["термин"]] + term["синонимы"] + term["объекты"]).lower()
            if query and query not in haystack:
                continue
            found.append({"направление": entry["код"], **term})
    return {"найдено": len(found), "термины": found}


HANDLERS = {
    "list_tracks": tool_list_tracks,
    "lookup_rule": tool_lookup_rule,
    "get_rule": tool_get_rule,
    "rules_by_category": tool_rules_by_category,
    "rules_for_object": tool_rules_for_object,
    "checklist": tool_checklist,
    "glossary_lookup": tool_glossary_lookup,
}


def handle(request, manifest):
    """Ответ на один запрос JSON-RPC; None — если ответ не нужен (уведомление)."""
    method = request.get("method")
    request_id = request.get("id")

    if method == "initialize":
        return {"protocolVersion": PROTOCOL,
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": "tiny1c", "version": "0.1.0"}}
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "resources/list":
        return {"resources": [{
            "uri": "tiny1c://manifest",
            "name": "Манифест правил tiny1C",
            "description": "Все направления, правила, глоссарии и сопоставление объектов",
            "mimeType": "application/json",
        }]}
    if method == "resources/read":
        uri = request.get("params", {}).get("uri", "")
        if uri != "tiny1c://manifest":
            raise ValueError("нет такого ресурса: %s" % uri)
        return {"contents": [{"uri": uri, "mimeType": "application/json",
                              "text": json.dumps(manifest, ensure_ascii=False)}]}
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        handler = HANDLERS.get(name)
        if handler is None:
            raise ValueError("нет такого инструмента: %s" % name)
        result = handler(manifest, params.get("arguments") or {})
        return {"content": [{"type": "text",
                             "text": json.dumps(result, ensure_ascii=False, indent=2)}]}
    raise ValueError("метод не поддерживается: %s" % method)


def main():
    manifest = load_manifest()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        request_id = request.get("id")
        try:
            result = handle(request, manifest)
        except Exception as error:  # ошибка инструмента возвращается вызывающему
            if request_id is None:
                continue
            response = {"jsonrpc": "2.0", "id": request_id,
                        "error": {"code": -32603, "message": str(error)}}
        else:
            if result is None or request_id is None:
                continue
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
