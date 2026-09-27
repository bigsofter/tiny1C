#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Сборка машинного манифеста tiny1C из правил, глоссариев и карт объектов.

Манифест (`manifest.json`) — единственное, что читает MCP-сервер: он не ходит
по каталогам и ничего не индексирует на лету. Здесь же проверяется то, во что
сервер потом верит:

  1. id правила совпадает с именем файла и уникален во всём наборе;
  2. направление правила совпадает с каталогом, в котором оно лежит, и у этого
     направления есть паспорт `track.md`;
  3. категория, серьёзность и платформы — из закрытых словарей;
  4. `источник` начинается с одного из видов: ошибка, измерение, эксперимент,
     образец, решение, документация. Правило без своего источника в набор не
     попадает — это и защита от пересказа чужих текстов, и признак того, что
     правило кто-то проверил;
  5. каждая запись `check` — «вид:описание», вид из закрытого словаря.
     Правило, которое не может назвать, чем ловится, — не правило;
  6. глоссарий разбирается как таблица с колонками термин/синонимы/объекты/
     пояснение;
  7. карточки инструментов `tools/<группа>/<инструмент>.md` — раздел
     «инструменты»: группа, исполнение, опасность и статус из закрытых словарей,
     непустая `идея` (для AGPL/GPL — с пометкой «только идея»), источник и check
     по тем же правилам, что у правил. Реализованный инструмент обязан иметь
     проверку вида `fixtures` — инструмент без фикстуры не публикуется.

Использование:
  scripts/manifest.py             собрать manifest.json
  scripts/manifest.py --проверить проверить без записи (1 при расхождениях)
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKS = os.path.join(ROOT, "tracks")
MANIFEST = os.path.join(ROOT, "manifest.json")

CATEGORIES = ["запросы", "модули", "формы-xml", "метаданные", "макеты", "процесс",
              "архитектура", "интерфейс", "данные", "интеграция"]
SEVERITIES = ["критично", "важно", "справка"]
PLATFORMS = ["8.3", "8.5"]
SOURCES = ["ошибка", "измерение", "эксперимент", "образец", "решение", "документация"]
CHECKS = ["lint", "checkconfig", "checkconfig-ext", "smoke-forms", "smoke-samples",
          "smoke-print", "fixtures", "refcheck", "xml-audit", "manual"]
RULE_REQUIRED = ["id", "направление", "категория", "серьёзность", "платформы",
                 "заголовок", "ключи", "источник", "check"]
TRACK_REQUIRED = ["код", "название", "вид", "платформы", "статус"]
TRACK_KINDS = ["ядро", "с-нуля", "типовая"]
TRACK_STATES = ["ведётся", "открыто"]

TOOLS_DIR = os.path.join(ROOT, "tools")
TOOL_REQUIRED = ["id", "группа", "инструмент", "сигнатура", "исполнение", "опасность",
                 "идея", "источник", "check", "статус", "правила"]
TOOL_GROUPS = ["introspection", "ops-copy", "debug", "ui", "help"]
TOOL_EXECUTION = ["offline", "agent-edt", "runner-copy", "runner-ro", "runner-ui"]
TOOL_DANGER = ["read", "write-copy", "exec-copy"]
TOOL_STATES = ["реализован", "карточка"]


def parse_scalar(raw):
    """Значение фронтматтера: строка в кавычках, плоский список или голая строка."""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        items, current, quote = [], "", None
        for ch in inner:
            if quote:
                if ch == quote:
                    quote = None
                else:
                    current += ch
            elif ch in "\"'":
                quote = ch
            elif ch == ",":
                items.append(current.strip())
                current = ""
            else:
                current += ch
        items.append(current.strip())
        return [item for item in items if item]
    if len(raw) > 1 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def read_document(path):
    """(фронтматтер, тело) файла; фронтматтер None, если блока --- ... --- нет."""
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    if not lines or lines[0].strip() != "---":
        return None, "\n".join(lines)
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None, "\n".join(lines)
    data = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, raw = line.split(":", 1)
        data[key.strip()] = parse_scalar(raw)
    return data, "\n".join(lines[end + 1:])


def read_glossary(path):
    """Глоссарий: строки markdown-таблицы термин | синонимы | объекты | пояснение."""
    terms = []
    if not os.path.exists(path):
        return terms
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line.startswith("|") or not line.endswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) != 4:
                continue
            if cells[0] in ("термин", "") or set(cells[0]) <= set("-: "):
                continue
            terms.append({
                "термин": cells[0],
                "синонимы": [item.strip() for item in cells[1].split(",")
                             if item.strip() and item.strip() != "—"],
                "объекты": [item.strip() for item in cells[2].split(",")
                            if item.strip() and item.strip() != "—"],
                "пояснение": cells[3],
            })
    return terms


def check_source(data, where, errors):
    """Источник начинается одним из видов словаря SOURCES."""
    source = data.get("источник", "")
    if not isinstance(source, str) or ":" not in source \
            or source.split(":", 1)[0] not in SOURCES:
        errors.append("%s: источник «%s» — нужен вид из списка: %s"
                      % (where, source, ", ".join(SOURCES)))


def check_checks(data, where, errors):
    """Непустой список check из записей «вид:описание». Возвращает список."""
    checks = data.get("check", [])
    if isinstance(checks, str):
        errors.append("%s: check должен быть списком" % where)
        checks = [checks]
    if not checks:
        errors.append("%s: пустой check — запись не говорит, чем ловится" % where)
    for entry in checks:
        kind = entry.split(":", 1)[0]
        if kind not in CHECKS:
            errors.append("%s: неизвестный вид проверки «%s» (нужен из: %s)"
                          % (where, kind, ", ".join(CHECKS)))
        if ":" not in entry or not entry.split(":", 1)[1].strip():
            errors.append("%s: проверка «%s» без описания" % (where, entry))
    return checks


def collect_tools(rule_ids, errors):
    """Карточки инструментов tools/<группа>/<инструмент>.md (кроме _TEMPLATE.md)."""
    tools = []
    if not os.path.isdir(TOOLS_DIR):
        return tools
    seen = set()
    for current, dirs, files in os.walk(TOOLS_DIR):
        dirs.sort()
        for name in sorted(files):
            if not name.endswith(".md") or name in ("_TEMPLATE.md", "README.md"):
                continue
            path = os.path.join(current, name)
            rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
            data, _ = read_document(path)
            if data is None:
                errors.append("%s: нет фронтматтера" % rel)
                continue
            for field in TOOL_REQUIRED:
                if field not in data:
                    errors.append("%s: нет поля «%s»" % (rel, field))
            tool_id = data.get("id", "")
            if not isinstance(tool_id, str) or not re.match(r"^[a-z]+-\d{3}$", tool_id):
                errors.append("%s: id «%s» не по формату «группа-001»" % (rel, tool_id))
            if tool_id in seen or tool_id in rule_ids:
                errors.append("%s: id «%s» уже занят в наборе" % (rel, tool_id))
            seen.add(tool_id)
            if data.get("инструмент") != name[:-3]:
                errors.append("%s: инструмент «%s» не совпадает с именем файла"
                              % (rel, data.get("инструмент")))
            group_dir = os.path.basename(current)
            if data.get("группа") != group_dir:
                errors.append("%s: группа «%s» не совпадает с каталогом «%s»"
                              % (rel, data.get("группа"), group_dir))
            for field, allowed in (("группа", TOOL_GROUPS), ("исполнение", TOOL_EXECUTION),
                                   ("опасность", TOOL_DANGER), ("статус", TOOL_STATES)):
                if data.get(field) not in allowed:
                    errors.append("%s: неизвестное значение «%s» поля «%s» (нужно из: %s)"
                                  % (rel, data.get(field), field, ", ".join(allowed)))
            idea = data.get("идея", "")
            if not isinstance(idea, str) or not idea.strip():
                errors.append("%s: пустая «идея» — откуда взят инструмент" % rel)
            elif re.search(r"\b(A?GPL|LGPL)", idea) and "только идея" not in idea:
                errors.append("%s: образец под (A|L)GPL — в «идея» нужна пометка «только идея»"
                              % rel)
            check_source(data, rel, errors)
            checks = check_checks(data, rel, errors)
            kinds = sorted({entry.split(":", 1)[0] for entry in checks})
            if data.get("статус") == "реализован" and "fixtures" not in kinds:
                errors.append("%s: реализованный инструмент без проверки вида fixtures" % rel)
            linked = data.get("правила", [])
            if not isinstance(linked, list):
                errors.append("%s: «правила» должны быть списком" % rel)
                linked = []
            for rule_id in linked:
                if rule_id not in rule_ids:
                    errors.append("%s: правила «%s» в наборе нет" % (rel, rule_id))
            card = dict(data)
            card["файл"] = rel
            card["виды_проверок"] = kinds
            tools.append(card)
    tools.sort(key=lambda card: card.get("id", ""))
    return tools


def collect():
    """Разбор дерева tracks. Возвращает (манифест, список ошибок)."""
    errors, tracks, rules = [], [], []
    seen_ids = set()
    for code in sorted(os.listdir(TRACKS)):
        track_dir = os.path.join(TRACKS, code)
        if not os.path.isdir(track_dir):
            continue
        passport_path = os.path.join(track_dir, "track.md")
        if not os.path.exists(passport_path):
            errors.append("%s: нет паспорта track.md" % code)
            continue
        passport, _ = read_document(passport_path)
        if passport is None:
            errors.append("%s/track.md: нет фронтматтера" % code)
            continue
        for field in TRACK_REQUIRED:
            if field not in passport:
                errors.append("%s/track.md: нет поля «%s»" % (code, field))
        if passport.get("код") != code:
            errors.append("%s/track.md: код «%s» не совпадает с каталогом"
                          % (code, passport.get("код")))
        if passport.get("вид") not in TRACK_KINDS:
            errors.append("%s/track.md: неизвестный вид «%s»" % (code, passport.get("вид")))
        if passport.get("статус") not in TRACK_STATES:
            errors.append("%s/track.md: неизвестный статус «%s»" % (code, passport.get("статус")))

        rules_dir = os.path.join(track_dir, "rules")
        track_rules = []
        if os.path.isdir(rules_dir):
            for name in sorted(os.listdir(rules_dir)):
                if not name.endswith(".md") or name == "README.md":
                    continue
                data, _ = read_document(os.path.join(rules_dir, name))
                if data is None:
                    errors.append("%s/%s: нет фронтматтера" % (code, name))
                    continue
                rule_id = data.get("id", "")
                if rule_id != name[:-3]:
                    errors.append("%s/%s: id «%s» не совпадает с именем файла"
                                  % (code, name, rule_id))
                if rule_id in seen_ids:
                    errors.append("%s/%s: id «%s» уже занят в наборе" % (code, name, rule_id))
                seen_ids.add(rule_id)
                for field in RULE_REQUIRED:
                    if field not in data:
                        errors.append("%s/%s: нет поля «%s»" % (code, name, field))
                if data.get("направление") != code:
                    errors.append("%s/%s: направление «%s» не совпадает с каталогом"
                                  % (code, name, data.get("направление")))
                if data.get("категория") not in CATEGORIES:
                    errors.append("%s/%s: неизвестная категория «%s»"
                                  % (code, name, data.get("категория")))
                if data.get("серьёзность") not in SEVERITIES:
                    errors.append("%s/%s: неизвестная серьёзность «%s»"
                                  % (code, name, data.get("серьёзность")))
                for platform in data.get("платформы", []):
                    if platform not in PLATFORMS:
                        errors.append("%s/%s: неизвестная платформа «%s»"
                                      % (code, name, platform))
                where = "%s/%s" % (code, name)
                check_source(data, where, errors)
                checks = check_checks(data, where, errors)
                rule = dict(data)
                rule["файл"] = "tracks/%s/rules/%s" % (code, name)
                rule["виды_проверок"] = sorted({entry.split(":", 1)[0] for entry in checks})
                rules.append(rule)
                track_rules.append(rule_id)

        glossary = read_glossary(os.path.join(track_dir, "glossary.md"))
        entry = dict(passport)
        entry["правил"] = len(track_rules)
        entry["правила"] = track_rules
        entry["терминов"] = len(glossary)
        entry["глоссарий"] = glossary
        entry["карта_объектов"] = ("tracks/%s/objects.md" % code
                                   if os.path.exists(os.path.join(track_dir, "objects.md"))
                                   else None)
        tracks.append(entry)

    by_object = {}
    for rule in rules:
        for obj in rule.get("объекты", []):
            by_object.setdefault(obj, []).append(rule["id"])
    for track in tracks:
        for term in track["глоссарий"]:
            for obj in term["объекты"]:
                by_object.setdefault(obj, [])

    manual_only = [rule["id"] for rule in rules if rule["виды_проверок"] == ["manual"]]
    tools = collect_tools({rule["id"] for rule in rules}, errors)
    manifest = {
        "версия": 1,
        "направлений": len(tracks),
        "правил": len(rules),
        "ловятся_только_человеком": manual_only,
        "объекты": {key: sorted(value) for key, value in sorted(by_object.items())},
        "направления": tracks,
        "правила": rules,
        "инструментов": len(tools),
        "инструменты": tools,
    }
    return manifest, errors


def main():
    dry_run = "--проверить" in sys.argv[1:] or "--check" in sys.argv[1:]
    manifest, errors = collect()
    body = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"

    for error in errors:
        print("ОШИБКА: %s" % error)

    if dry_run:
        stale = True
        if os.path.exists(MANIFEST):
            with open(MANIFEST, encoding="utf-8") as handle:
                stale = handle.read() != body
        if stale:
            print("ОШИБКА: manifest.json разошёлся с правилами — пересобрать scripts/manifest.py")
        if errors or stale:
            return 1
        print("Манифест: направлений %d, правил %d" % (manifest["направлений"], manifest["правил"]))
        return 0

    if errors:
        print("Манифест не записан: сначала разобрать ошибки выше.")
        return 1

    with open(MANIFEST, "w", encoding="utf-8") as handle:
        handle.write(body)
    print("Записан manifest.json: направлений %d, правил %d, только человеком ловятся %d, "
          "инструментов %d"
          % (manifest["направлений"], manifest["правил"],
             len(manifest["ловятся_только_человеком"]), manifest["инструментов"]))
    for track in manifest["направления"]:
        print("  %-11s %-42s правил %2d, терминов %2d"
              % (track["код"], track["название"], track["правил"], track["терминов"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
