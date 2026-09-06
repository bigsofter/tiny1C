#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Выгрузка правил одним файлом — для систем без поддержки MCP.

Не всякий агент умеет MCP: веб-чаты, простые обёртки над API, корпоративные
песочницы без права запускать процессы. Туда правила заезжают обычным текстом:
компактный свод кладётся в системную подсказку или в файл проектных инструкций
(AGENTS.md, .cursorrules, «знания» ассистента).

По умолчанию собирается оглавление — заголовок, ключи и чем ловится: этого
хватает, чтобы агент знал о существовании правила и спросил полный текст.
Ключ `--полный` включает тексты целиком: точнее, но заметно дороже по контексту.

Использование:
  scripts/export.py                                  свод по всем направлениям
  scripts/export.py --направление core,greenfield    только выбранные
  scripts/export.py --платформа 8.3                  только применимые к 8.3
  scripts/export.py --полный --выход dist/rules.md   полные тексты в файл
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "manifest.json")
SEVERITY_ORDER = {"критично": 0, "важно": 1, "справка": 2}


def parse_args(argv):
    options = {"направление": None, "платформа": None, "полный": False, "выход": None}
    index = 0
    while index < len(argv):
        item = argv[index]
        if item in ("--помощь", "-h", "--help"):
            print(__doc__.strip())
            sys.exit(0)
        elif item == "--полный":
            options["полный"] = True
        elif item in ("--направление", "--платформа", "--выход"):
            index += 1
            if index >= len(argv):
                print("Не хватает значения для %s" % item)
                sys.exit(2)
            options[item[2:]] = argv[index]
        else:
            print("Неизвестный ключ: %s" % item)
            sys.exit(2)
        index += 1
    return options


def rule_body(rule):
    """Текст правила без фронтматтера."""
    path = os.path.join(ROOT, rule["файл"])
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    if lines and lines[0].strip() == "---":
        try:
            return "\n".join(lines[lines.index("---", 1) + 1:]).strip()
        except ValueError:
            pass
    return "\n".join(lines).strip()


def main():
    options = parse_args(sys.argv[1:])
    with open(MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)

    tracks = None
    if options["направление"]:
        tracks = [code.strip() for code in options["направление"].split(",") if code.strip()]
        known = {track["код"] for track in manifest["направления"]}
        unknown = [code for code in tracks if code not in known]
        if unknown:
            print("Нет таких направлений: %s. Есть: %s"
                  % (", ".join(unknown), ", ".join(sorted(known))))
            return 1

    rules = [rule for rule in manifest["правила"]
             if (tracks is None or rule["направление"] in tracks)
             and (options["платформа"] is None
                  or options["платформа"] in rule.get("платформы", []))]
    rules.sort(key=lambda rule: (rule["направление"],
                                 SEVERITY_ORDER.get(rule["серьёзность"], 9),
                                 rule["id"]))

    out = []
    out.append("# Правила разработки 1С (tiny1C)")
    out.append("")
    out.append("Выгрузка из набора https://github.com/bigsofter/tiny1C. Каждое правило "
               "выведено из реальной ошибки, измерения или эксперимента и называет, "
               "чем оно ловится.")
    отбор = []
    if tracks:
        отбор.append("направления: " + ", ".join(tracks))
    if options["платформа"]:
        отбор.append("платформа: " + options["платформа"])
    if отбор:
        out.append("")
        out.append("Отбор — " + "; ".join(отбор) + ".")
    out.append("")
    out.append("Правил в выгрузке: %d." % len(rules))

    for track in manifest["направления"]:
        if tracks is not None and track["код"] not in tracks:
            continue
        track_rules = [rule for rule in rules if rule["направление"] == track["код"]]
        if not track_rules and not track["глоссарий"]:
            continue
        out.append("")
        out.append("## %s (%s)" % (track["название"], track["код"]))
        if track.get("конфигурации"):
            out.append("")
            out.append("Конфигурации: " + ", ".join(track["конфигурации"]) + ".")

        if track_rules:
            out.append("")
            for rule in track_rules:
                out.append("### %s — %s" % (rule["id"], rule["заголовок"]))
                out.append("")
                out.append("*%s · платформы %s · ловится: %s*"
                           % (rule["серьёзность"],
                              "/".join(rule.get("платформы", [])),
                              "; ".join(rule.get("check", []))))
                out.append("")
                if options["полный"]:
                    out.append(rule_body(rule))
                else:
                    out.append("Ключи: " + ", ".join(rule.get("ключи", [])) + ".")
                    out.append("")
                    out.append("Полный текст: `%s`." % rule["файл"])
                out.append("")

        if track["глоссарий"]:
            out.append("### Глоссарий")
            out.append("")
            for term in track["глоссарий"]:
                objects = (" [%s]" % ", ".join(term["объекты"])) if term["объекты"] else ""
                out.append("- **%s**%s — %s" % (term["термин"], objects, term["пояснение"]))
            out.append("")

    body = "\n".join(out).rstrip() + "\n"

    if options["выход"]:
        path = os.path.join(ROOT, options["выход"]) if not os.path.isabs(options["выход"]) \
            else options["выход"]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(body)
        print("Записано: %s (правил %d, %d КБ)"
              % (options["выход"], len(rules), len(body.encode("utf-8")) // 1024))
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
