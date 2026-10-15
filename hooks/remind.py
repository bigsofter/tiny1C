#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Мягкие хуки плагина tiny1C: напоминания агенту. Ничего не блокируют.

PreToolUse (Edit|Write|MultiEdit): правится файл 1С (.bsl, .form, .mdo, .mxlx или
XML внутри выгрузки конфигурации) - одно короткое напоминание вызвать checklist,
раз на расширение за сессию.
Stop: один раз за сессию и только если в ней правились такие файлы - строка
«если было новое знание о платформе, предложи его командой /1c:propose-rule».

Состояние сессии - json в ${CLAUDE_PLUGIN_DATA}/state (или во временном каталоге).
При любой ошибке хук молча выходит с кодом 0. Только stdlib, Python 3.8+.
"""

import json
import os
import re
import sys
import tempfile
import time

CHECKLIST_EXTENSIONS = {".bsl", ".form", ".mdo", ".mxlx", ".xml"}
DUMP_PARTS = {"ext", "forms", "templates", "commonmodules", "documents", "catalogs",
              "dataprocessors", "reports", "subsystems", "roles", "commonforms",
              "informationregisters", "accumulationregisters", "enums"}
STATE_TTL = 14 * 24 * 3600


def state_dir():
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(tempfile.gettempdir(), "tiny1c-plugin")
    return os.path.join(base, "state")


def state_path(session_id):
    return os.path.join(state_dir(), re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:80] + ".json")


def load_state(session_id):
    try:
        with open(state_path(session_id), encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {"reminded": [], "edited": False, "stopped": False}


def save_state(session_id, state):
    os.makedirs(state_dir(), exist_ok=True)
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
    for _ in range(6):  # Configuration.xml лежит в корне выгрузки
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
    state["edited"] = True
    remind = extension not in state["reminded"]
    if remind:
        state["reminded"].append(extension)
    save_state(session_id, state)
    if remind:
        emit("PreToolUse",
             "Файл 1С (%s): если в этой сессии ещё не вызывал tiny1c checklist(file=\"%s\", "
             "compact=true) - вызови его до правки." % (extension, extension))


def on_stop(data, session_id):
    if data.get("stop_hook_active"):
        return
    state = load_state(session_id)
    if not state.get("edited") or state.get("stopped"):
        return
    state["stopped"] = True
    save_state(session_id, state)
    emit("Stop",
         "Если в этой задаче было новое знание о платформе 1С, которого нет в наборе tiny1C, - "
         "предложи человеку записать его командой /1c:propose-rule. Если нового не было, "
         "ответь одной короткой фразой.")


def main():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace") or "{}")
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return
    event = data.get("hook_event_name")
    if event == "PreToolUse":
        on_pre_tool_use(data, session_id)
    elif event == "Stop":
        on_stop(data, session_id)


if __name__ == "__main__":
    try:
        main()
    except BaseException:  # хук не должен мешать работе ни при каких обстоятельствах
        pass
    sys.exit(0)
