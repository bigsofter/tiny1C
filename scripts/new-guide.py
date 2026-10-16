#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Заготовка нового рецепта «как сделать»: файл из шаблона в нужном направлении.

Скрипт не думает за автора — он только раскладывает поля по местам, проверяет,
что направление существует, а идентификатор свободен, и напоминает, что
`источник`, `задача`, `check` и ссылки `правила` обязательны.

Использование:
  scripts/new-guide.py <направление> <id> [заголовок]

Примеры:
  scripts/new-guide.py core how-007
  scripts/new-guide.py core how-007 "Собрать расширение из исходников и применить его"
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "tracks", "_GUIDE_TEMPLATE.md")
DEFAULT_TITLE = "Одна фраза: что получаем и в каком окружении"


def id_taken(guide_id):
    """Путь, под которым id уже занят правилом, рецептом или карточкой инструмента."""
    tracks = os.path.join(ROOT, "tracks")
    for other in sorted(os.listdir(tracks)):
        for folder in ("rules", "guides"):
            candidate = os.path.join(tracks, other, folder, guide_id + ".md")
            if os.path.exists(candidate):
                return candidate
    tools = os.path.join(ROOT, "tools")
    for current, _dirs, files in os.walk(tools):
        if guide_id + ".md" in files:
            return os.path.join(current, guide_id + ".md")
    return None


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(__doc__.strip())
        return 2
    track, guide_id = args[0], args[1]
    title = args[2] if len(args) > 2 else DEFAULT_TITLE

    track_dir = os.path.join(ROOT, "tracks", track)
    if not os.path.isdir(track_dir):
        available = sorted(name for name in os.listdir(os.path.join(ROOT, "tracks"))
                           if os.path.isdir(os.path.join(ROOT, "tracks", name)))
        print("Нет направления «%s». Есть: %s" % (track, ", ".join(available)))
        return 1
    if not re.match(r"^how-\d{3}$", guide_id):
        print("Идентификатор рецепта пишется как «how-001»: how, дефис, три цифры.")
        return 1

    taken = id_taken(guide_id)
    if taken:
        print("Идентификатор «%s» уже занят: %s" % (guide_id, os.path.relpath(taken, ROOT)))
        return 1

    guides_dir = os.path.join(track_dir, "guides")
    os.makedirs(guides_dir, exist_ok=True)
    path = os.path.join(guides_dir, guide_id + ".md")

    with open(TEMPLATE, encoding="utf-8") as handle:
        body = handle.read()
    lines = body.split("\n")
    for number, line in enumerate(lines):
        if line.startswith("id: "):
            lines[number] = "id: " + guide_id
        elif line.startswith("направление: "):
            lines[number] = "направление: " + track
        elif line.startswith("заголовок: "):
            lines[number] = 'заголовок: "%s"' % title
        elif line.startswith("# "):
            lines[number] = "# " + title
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    print("Создано: %s" % os.path.relpath(path, ROOT))
    print("Заполнить обязательно: категория, источник (практика:проект и дата), задача, "
          "check (вид:описание), правила (id из lookup_rule).")
    print("Потом: scripts/manifest.py && scripts/hygiene.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
