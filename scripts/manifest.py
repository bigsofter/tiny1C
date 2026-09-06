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
     пояснение.

Использование:
  scripts/manifest.py             собрать manifest.json
  scripts/manifest.py --проверить проверить без записи (1 при расхождениях)
"""

import json
import os
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
                source = data.get("источник", "")
                if not isinstance(source, str) or ":" not in source \
                        or source.split(":", 1)[0] not in SOURCES:
                    errors.append("%s/%s: источник «%s» — нужен вид из списка: %s"
                                  % (code, name, source, ", ".join(SOURCES)))
                checks = data.get("check", [])
                if isinstance(checks, str):
                    errors.append("%s/%s: check должен быть списком" % (code, name))
                    checks = [checks]
                if not checks:
                    errors.append("%s/%s: пустой check — правило не говорит, чем ловится"
                                  % (code, name))
                for entry in checks:
                    kind = entry.split(":", 1)[0]
                    if kind not in CHECKS:
                        errors.append("%s/%s: неизвестный вид проверки «%s» (нужен из: %s)"
                                      % (code, name, kind, ", ".join(CHECKS)))
                    if ":" not in entry or not entry.split(":", 1)[1].strip():
                        errors.append("%s/%s: проверка «%s» без описания" % (code, name, entry))
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
    manifest = {
        "версия": 1,
        "направлений": len(tracks),
        "правил": len(rules),
        "ловятся_только_человеком": manual_only,
        "объекты": {key: sorted(value) for key, value in sorted(by_object.items())},
        "направления": tracks,
        "правила": rules,
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
    print("Записан manifest.json: направлений %d, правил %d, только человеком ловятся %d"
          % (manifest["направлений"], manifest["правил"],
             len(manifest["ловятся_только_человеком"])))
    for track in manifest["направления"]:
        print("  %-11s %-42s правил %2d, терминов %2d"
              % (track["код"], track["название"], track["правил"], track["терминов"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
