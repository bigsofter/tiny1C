#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Проверка гигиены перед публикацией: что не должно уехать в публичный набор.

Набор правил пишется по следам живых проектов, поэтому в текст легко попадает
то, чему в публичном репозитории не место: имя заказчика, логин тестовой базы,
путь с домашним каталогом разработчика, кусок чужого корпуса правил. Глазами
это не удержать — проверка механическая и запускается перед каждым push.

Что ищется:

  1. приватное — имена заказчиков, логины, пароли, токены, ключи, IP;
  2. пути машины разработчика — /Users/…, /home/…, C:\\…, ~/Dev, ~/EDT;
  3. следы чужих корпусов правил — заимствованный текст вместо своего;
  4. артефакты 1С и просто бинарники — .cf, .epf, .dt, базы, архивы;
  5. правила без поля «источник» — правило, о котором неизвестно, откуда оно;
  6. расхождение README с манифестом — таблица направлений отстала от набора.

Разрешённые исключения — в scripts/hygiene-allow.txt: строка «путь<TAB>маркер».
Каждое исключение объясняется комментарием: молчаливое подавление здесь опаснее
самой находки.

Использование:
  scripts/hygiene.py            проверить дерево (1 при находках)
  scripts/hygiene.py --список   показать, что именно ищется
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW_FILE = os.path.join(ROOT, "scripts", "hygiene-allow.txt")
MANIFEST_FILE = os.path.join(ROOT, "manifest.json")
README_FILE = os.path.join(ROOT, "README.md")
SKIP_DIRS = {".git", "__pycache__", ".idea", ".vscode"}
MAX_BYTES = 512 * 1024

# (имя проверки, регулярное выражение, пояснение)
PATTERNS = [
    ("заказчик", r"(?i)\bdrissotex\b", "имя заказчика"),
    ("логин", r"(?i)\btinycio-1c\b", "логин тестовой базы"),
    ("пароль", r"(?i)(password|пароль)\s*[=:]\s*\S+", "пароль в тексте"),
    ("переменная-пароля", r"\b(SMOKE_PWD|DIST_PWD|DB_PASSWORD)\s*=\s*\S+", "пароль в переменной"),
    ("токен", r"\b(ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{20,})\b",
     "токен доступа"),
    ("приватный-ключ", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "приватный ключ"),
    ("путь-mac", r"/Users/[A-Za-z0-9._-]+/", "путь с домашним каталогом"),
    ("путь-linux", r"/home/[A-Za-z0-9._-]+/", "путь с домашним каталогом"),
    ("путь-windows", r"[A-Za-z]:\\\\?Users\\\\?", "путь с домашним каталогом"),
    ("путь-проекта", r"~/(Dev|EDT|Documents)/", "путь машины разработчика"),
    ("ip", r"(?i)(?:https?://|\bip\b[\s:=]+|host[\s:=]+|сервер[\s:=]+)(?:\d{1,3}\.){3}\d{1,3}\b", "IP-адрес хоста"),
    ("чужой-корпус-unica", r"(?i)(IngvarConsulting|\bunica\.[a-z]+\.|INV\.[A-Z]+\.|CTR\.[A-Z]+\.)",
     "след заимствованного корпуса Unica"),
    ("чужой-корпус-comol", r"(?i)(ai_rules_1c|\bcomol\b)", "след заимствованного корпуса comol"),
]

BINARY_SUFFIXES = {".cf", ".cfu", ".cfe", ".epf", ".erf", ".dt", ".1cd", ".zip", ".7z",
                   ".rar", ".gz", ".tar", ".png", ".jpg", ".jpeg", ".pdf", ".xlsx", ".docx"}
TEXT_SUFFIXES = {".md", ".py", ".json", ".yml", ".yaml", ".txt", ".sh", ".toml", ".cfg"}


def read_allow():
    """Исключения: множество пар (относительный путь, имя проверки)."""
    allow = set()
    if not os.path.exists(ALLOW_FILE):
        return allow
    with open(ALLOW_FILE, encoding="utf-8") as handle:
        for line in handle:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                continue
            allow.add((parts[0], parts[1]))
    return allow


def walk():
    for current, dirs, files in os.walk(ROOT):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            path = os.path.join(current, name)
            if path == ALLOW_FILE:
                continue  # файл исключений по определению перечисляет искомые маркеры
            yield path, os.path.relpath(path, ROOT)


def check_sources(findings):
    """Каждое правило обязано называть свой источник."""
    tracks = os.path.join(ROOT, "tracks")
    if not os.path.isdir(tracks):
        return
    for code in sorted(os.listdir(tracks)):
        rules_dir = os.path.join(tracks, code, "rules")
        if not os.path.isdir(rules_dir):
            continue
        for name in sorted(os.listdir(rules_dir)):
            if not name.endswith(".md") or name == "README.md":
                continue
            path = os.path.join(rules_dir, name)
            with open(path, encoding="utf-8") as handle:
                head = handle.read(2000)
            if "\nисточник:" not in head:
                findings.append((os.path.relpath(path, ROOT), 0, "источник",
                                 "правило без поля «источник»"))


def check_readme(findings):
    """Таблица направлений в README обязана совпадать с манифестом.

    Счётчики правил и терминов в README ставятся руками, а растут при каждом
    новом правиле, поэтому расходятся молча: читатель видит одно число, сервер
    отдаёт другое. Сверка механическая — ошибка ловится на push, а не глазами.

    Ожидаемый вид строки: «| `код` | что покрывает | правил | терминов |»,
    где правил — число либо «открыто» для направления без правил, а терминов —
    число либо «—», если глоссария ещё нет.
    """
    if not (os.path.exists(MANIFEST_FILE) and os.path.exists(README_FILE)):
        return
    with open(MANIFEST_FILE, encoding="utf-8") as handle:
        manifest = json.load(handle)
    with open(README_FILE, encoding="utf-8") as handle:
        lines = handle.readlines()

    rows = {}
    for number, line in enumerate(lines, 1):
        match = re.match(r"^\|\s*`([a-z0-9_-]+)`\s*\|[^|]*\|([^|]*)\|([^|]*)\|", line)
        if match:
            rows[match.group(1)] = (number, match.group(2).strip(), match.group(3).strip())

    rel = os.path.relpath(README_FILE, ROOT)
    for track in manifest.get("направления", []):
        code = track["код"]
        if code not in rows:
            findings.append((rel, 0, "README",
                             "направления «%s» нет в таблице" % code))
            continue
        number, rules, terms = rows[code]
        want_rules = "открыто" if track["статус"] == "открыто" else str(track["правил"])
        want_terms = "—" if not track["терминов"] else str(track["терминов"])
        if rules != want_rules:
            findings.append((rel, number, "README",
                             "%s: правил в таблице «%s», в манифесте «%s»"
                             % (code, rules, want_rules)))
        if terms != want_terms:
            findings.append((rel, number, "README",
                             "%s: терминов в таблице «%s», в манифесте «%s»"
                             % (code, terms, want_terms)))

    known = {track["код"] for track in manifest.get("направления", [])}
    for code, (number, _, _) in sorted(rows.items()):
        if code not in known:
            findings.append((rel, number, "README",
                             "направления «%s» в наборе нет" % code))


def main():
    if "--список" in sys.argv[1:]:
        print("Проверки гигиены:")
        for name, _, note in PATTERNS:
            print("  %-22s %s" % (name, note))
        print("  %-22s %s" % ("бинарник", "запрещённые расширения и файлы больше 512 КБ"))
        print("  %-22s %s" % ("источник", "правило без поля «источник»"))
        print("  %-22s %s" % ("README", "таблица направлений против манифеста"))
        return 0

    allow = read_allow()
    findings = []
    compiled = [(name, re.compile(pattern), note) for name, pattern, note in PATTERNS]

    for path, rel in walk():
        suffix = os.path.splitext(path)[1].lower()
        if suffix in BINARY_SUFFIXES:
            if (rel, "бинарник") not in allow:
                findings.append((rel, 0, "бинарник", "запрещённое расширение %s" % suffix))
            continue
        size = os.path.getsize(path)
        if size > MAX_BYTES and (rel, "бинарник") not in allow:
            findings.append((rel, 0, "бинарник", "файл больше 512 КБ (%d байт)" % size))
        if suffix not in TEXT_SUFFIXES and suffix != "":
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.readlines()
        except (UnicodeDecodeError, PermissionError):
            findings.append((rel, 0, "бинарник", "файл не читается как UTF-8"))
            continue
        for number, line in enumerate(lines, 1):
            for name, pattern, note in compiled:
                if (rel, name) in allow:
                    continue
                if pattern.search(line):
                    findings.append((rel, number, name, note))

    check_sources(findings)
    check_readme(findings)

    if not findings:
        print("Гигиена: чисто — приватного, чужих корпусов и бинарников не найдено.")
        return 0

    print("Гигиена: находок %d" % len(findings))
    for rel, number, name, note in findings:
        place = "%s:%d" % (rel, number) if number else rel
        print("  %-52s %-22s %s" % (place, name, note))
    print("\nЛибо убрать находку, либо внести исключение в scripts/hygiene-allow.txt"
          " с объяснением.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
