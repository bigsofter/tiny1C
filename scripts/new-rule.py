#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Заготовка нового правила: файл из шаблона в нужном направлении.

Скрипт не думает за автора — он только раскладывает поля по местам, проверяет,
что направление существует, а идентификатор свободен, и напоминает, что
`источник` и `check` обязательны.

Использование:
  scripts/new-rule.py <направление> <id> [заголовок]

Примеры:
  scripts/new-rule.py core forms-011
  scripts/new-rule.py unf unf-003 "Заказ покупателя закрывается расходной"
"""

import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "tracks", "_TEMPLATE.md")


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__.strip())
        return 2
    track, rule_id = args[0], args[1]
    title = args[2] if len(args) > 2 else "Одна фраза: что именно нельзя или что именно надо"

    track_dir = os.path.join(ROOT, "tracks", track)
    if not os.path.isdir(track_dir):
        available = sorted(name for name in os.listdir(os.path.join(ROOT, "tracks"))
                           if os.path.isdir(os.path.join(ROOT, "tracks", name)))
        print("Нет направления «%s». Есть: %s" % (track, ", ".join(available)))
        return 1
    if not re.match(r"^[a-z][a-z0-9-]*-\d{3}$", rule_id):
        print("Идентификатор пишется как «тема-001»: буквы, дефис, три цифры.")
        return 1

    rules_dir = os.path.join(track_dir, "rules")
    os.makedirs(rules_dir, exist_ok=True)
    path = os.path.join(rules_dir, rule_id + ".md")
    if os.path.exists(path):
        print("Правило «%s» уже есть: %s" % (rule_id, os.path.relpath(path, ROOT)))
        return 1
    for other in os.listdir(os.path.join(ROOT, "tracks")):
        candidate = os.path.join(ROOT, "tracks", other, "rules", rule_id + ".md")
        if os.path.exists(candidate):
            print("Идентификатор занят в другом направлении: %s"
                  % os.path.relpath(candidate, ROOT))
            return 1

    with open(TEMPLATE, encoding="utf-8") as handle:
        body = handle.read()
    body = body.replace("id: ЗАМЕНИТЬ", "id: " + rule_id)
    body = body.replace("направление: ЗАМЕНИТЬ", "направление: " + track)
    body = body.replace('заголовок: "Одна фраза: что именно нельзя или что именно надо"',
                        'заголовок: "%s"' % title)
    body = body.replace("# Заголовок правила", "# " + title)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)

    print("Создано: %s" % os.path.relpath(path, ROOT))
    print("Заполнить обязательно: категория, источник (вид:проект и дата), check (вид:описание).")
    print("Потом: scripts/manifest.py && scripts/hygiene.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
