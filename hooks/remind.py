#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Мягкий хук плагина tiny1C: напоминание агенту. Ничего не блокирует.

PreToolUse (Edit|Write|MultiEdit): правится файл 1С (.bsl, .form, .mdo, .mxlx или
XML внутри выгрузки конфигурации) - одно короткое напоминание вызвать checklist,
раз на расширение за сессию. При первой за сессию правке 1С-файла в тот же текст
добавлено: если найдёшь новое знание о платформе - в конце предложи /1c:propose-rule.

Состояние сессии - json в ${CLAUDE_PLUGIN_DATA}/state (или в пользовательском
временном каталоге). При любой ошибке хук молча выходит с кодом 0.
Только stdlib, Python 3.8+.
"""

import json
import os
import re
import sys
import tempfile
import time

CHECKLIST_EXTENSIONS = {".bsl", ".form", ".mdo", ".mxlx", ".xml"}
# Папки выгрузки, которые почти не встречаются вне 1С (общие «templates», «forms», «reports»
# сюда намеренно не входят - для них нужен Configuration.xml выше по дереву).
DUMP_PARTS = {"commonmodules", "documents", "catalogs", "dataprocessors", "subsystems",
              "commonforms", "informationregisters", "accumulationregisters", "enums"}
STATE_TTL = 14 * 24 * 3600


def state_dir():
    base = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not base:  # вне плагина: каталог именно этого пользователя, не общий /tmp
        who = str(os.getuid()) if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")
        base = os.path.join(tempfile.gettempdir(), "tiny1c-plugin-" + re.sub(r"[^A-Za-z0-9_-]", "_", who))
    return os.path.join(base, "state")


def state_path(session_id):
    return os.path.join(state_dir(), re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:80] + ".json")


def load_state(session_id):
    try:
        with open(state_path(session_id), encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("reminded"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"reminded": []}


def save_state(session_id, state):
    os.makedirs(state_dir(), mode=0o700, exist_ok=True)
    with open(state_path(session_id), "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    cleanup()


def cleanup():
    """Старые файлы состояния (сессии давно закончились) убираются между делом."""
    try:
        now = time.time()
        for name in os.listdir(state_dir()):
            path = os.path.join(state_dir(), name)
            if name.endswith(".json") and now - os.path.getmtime(path) > STATE_TTL:
                os.remove(path)
    except OSError:
        pass


def is_1c_file(path):
    """Файл 1С по расширению; для .xml - только внутри выгрузки конфигурации."""
    extension = os.path.splitext(path)[1].lower()
    if extension not in CHECKLIST_EXTENSIONS:
        return None
    if extension != ".xml":
        return extension
    folder = os.path.dirname(os.path.abspath(path))
    parts = {part.lower() for part in folder.replace("\\", "/").split("/")}
    if parts & DUMP_PARTS:
        return extension
    for _ in range(10):  # Configuration.xml лежит в корне выгрузки
        if os.path.exists(os.path.join(folder, "Configuration.xml")):
            return extension
        parent = os.path.dirname(folder)
        if parent == folder:
            break
        folder = parent
    return None


def emit(event, text):
    # ensure_ascii: вывод не зависит от кодировки консоли (на Windows - cp1251)
    sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": event,
                                                        "additionalContext": text}}))


def on_pre_tool_use(data, session_id):
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("path") or ""
    extension = is_1c_file(path) if isinstance(path, str) and path else None
    if not extension:
        return
    state = load_state(session_id)
    if extension in state["reminded"]:
        return
    first = not state["reminded"]
    state["reminded"].append(extension)
    save_state(session_id, state)
    text = ("Файл 1С (%s): если в этой сессии ещё не вызывал tiny1c checklist(file=\"%s\", "
            "compact=true) - вызови его до правки." % (extension, extension))
    if first:
        text += (" Если по ходу задачи найдёшь новое знание о платформе 1С, которого нет в наборе, - "
                 "в конце предложи записать его командой /1c:propose-rule.")
    emit("PreToolUse", text)


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return
    if data.get("hook_event_name") == "PreToolUse":
        on_pre_tool_use(data, session_id)


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # хук не должен мешать работе ни при каких обстоятельствах
        pass
    sys.exit(0)
