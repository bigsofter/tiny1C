#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Счётчики README по манифесту: таблица направлений и доля «только человеком».

`scripts/hygiene.py` сверяет README с манифестом и падает, если числа отстали.
Этот скрипт их ставит: правило, пришедшее PR-ом `intake/*` из портала, не
должно требовать ручной правки README, иначе обязательная проверка `intake`
висела бы на каждом таком PR.

Что меняется (и только это):

  1. в строках таблицы «| `код` | что покрывает | правил | терминов |» —
     колонки «правил» (число или «открыто») и «терминов» (число или «—»),
     по тем же правилам, что в `hygiene.check_readme`;
  2. направление из манифеста, которого в таблице нет, получает строку после
     последней строки таблицы; «что покрывает» берётся из `название` его
     `track.md`;
  3. фраза «таких сейчас N из M» — правила, ловимые только человеком, из всех.

Строки направлений, которых в манифесте нет, не удаляются: это решение
человека, и hygiene.py про них скажет сам.

Использование:
  scripts/readme-counts.py             переписать README.md
  scripts/readme-counts.py --проверить  только проверить (1 при расхождении)
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_FILE = os.path.join(ROOT, "manifest.json")
README_FILE = os.path.join(ROOT, "README.md")

# Тот же разбор строки, что в hygiene.check_readme: правишь одну сторону — правь вторую.
ROW = re.compile(r"^(\|\s*`([a-z0-9_-]+)`\s*\|[^|]*\|)([^|]*)\|([^|]*)\|(.*)$")
MANUAL = re.compile(r"таких сейчас (\d+) из (\d+)")


def want_counts(track):
    rules = "открыто" if track["статус"] == "открыто" else str(track["правил"])
    terms = "—" if not track["терминов"] else str(track["терминов"])
    return rules, terms


def cell(value):
    """Ячейка таблицы в принятом виде: пробел, значение, пробел."""
    return " %s " % value


def rewrite(text, manifest):
    """Новый текст README по манифесту."""
    lines = text.split("\n")
    tracks = {track["код"]: track for track in manifest.get("направления", [])}
    seen, last_row = set(), -1
    for index, line in enumerate(lines):
        match = ROW.match(line)
        if not match:
            continue
        last_row = index
        code = match.group(2)
        seen.add(code)
        if code not in tracks:
            continue
        rules, terms = want_counts(tracks[code])
        lines[index] = "%s%s|%s|%s" % (match.group(1), cell(rules), cell(terms), match.group(5))

    missing = [track for code, track in sorted(tracks.items()) if code not in seen]
    if missing:
        if last_row < 0:
            raise SystemExit("README: таблицы направлений нет — некуда добавить %s"
                             % ", ".join(track["код"] for track in missing))
        added = []
        for track in missing:
            rules, terms = want_counts(track)
            title = str(track.get("название", "")).replace("|", "/").strip() or track["код"]
            added.append("| `%s` | %s | %s | %s |" % (track["код"], title, rules, terms))
        lines[last_row + 1:last_row + 1] = added

    manual = len(manifest.get("ловятся_только_человеком", []))
    total = manifest.get("правил", 0)
    out = "\n".join(lines)
    return MANUAL.sub("таких сейчас %d из %d" % (manual, total), out)


def main():
    check = "--проверить" in sys.argv[1:] or "--check" in sys.argv[1:]
    with open(MANIFEST_FILE, encoding="utf-8") as handle:
        manifest = json.load(handle)
    with open(README_FILE, encoding="utf-8") as handle:
        text = handle.read()
    body = rewrite(text, manifest)
    if body == text:
        print("README: счётчики совпадают с манифестом.")
        return 0
    if check:
        print("ОШИБКА: README разошёлся с манифестом — пересобрать scripts/readme-counts.py")
        return 1
    with open(README_FILE, "w", encoding="utf-8") as handle:
        handle.write(body)
    print("README: счётчики обновлены по манифесту.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
