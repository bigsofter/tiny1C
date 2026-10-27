# -*- coding: utf-8 -*-
"""Текст пакета инструкций для промпта: что из файлов пакета уходит помощнику, а что остаётся для ревью.

Файлы пакета (where_is.md, notes.md, objects.md, faq.md) пишутся как справочник:
с пометками «проверить», колонками статуса и ссылками на источники. В промпт
помощника они идут в сжатом виде. Правила сжатия — здесь, одним местом, чтобы и
сервер (get_instructions), и проверка манифеста (потолок размера) считали одно
и то же:

  1. строка с пометкой `[проверить]` в промпт не попадает — неподтверждённый
     факт помощнику не даётся вовсе (безопаснее, чем давать с оговоркой);
  2. раздел, чей заголовок кончается на `(подробно)`, в промпт не попадает —
     он для чтения по запросу (инструмент get_instructions_file);
  3. в таблицах убираются колонки «статус» и «источник»;
  4. ссылки на источники в скобках — `(S-5)`, `(S-5, S-6; с 3.0.144)`,
     `(опыт)`, `(из промпта)` — убираются; сноски с URL в пакете запрещены
     и так (они в sources.md, который в пакет не входит);
  5. заголовок файла (первая строка `# …`) убирается — раздел подписывает сборщик
     пакета; при вклейке в пакет заголовки файла опускаются на уровень (## -> ###);
  6. пустые строки схлопываются.

Отдельно — `size_of(text)`: размер в байтах UTF-8, по нему считается потолок.
"""

import re

UNVERIFIED = "[проверить]"
DETAIL_SUFFIX = "(подробно)"
DROP_COLUMNS = {"статус", "источник", "статус / источник", "статус/источник"}
SOURCE_REF = re.compile(r"\s*\((?:S-\d+|опыт|из промпта)[^()]*\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def is_table_row(line):
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def split_row(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def join_row(cells):
    return "| " + " | ".join(cells) + " |"


def is_separator(cells):
    return all(set(cell) <= set("-: ") and cell for cell in cells)


def prompt_lines(text):
    """Строки файла пакета, пригодные для промпта (правила 1–5 из описания модуля)."""
    out = []
    skip_level = None       # уровень заголовка раздела «(подробно)», который сейчас пропускаем
    drop = None             # индексы колонок текущей таблицы, которые убираем
    first = True
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if first and line.strip():
            first = False
            if line.startswith("# "):
                continue
        match = HEADING.match(line)
        if match:
            level, title = len(match.group(1)), match.group(2)
            if skip_level is not None and level <= skip_level:
                skip_level = None
            if skip_level is None and title.endswith(DETAIL_SUFFIX):
                skip_level = level
            drop = None
        if skip_level is not None:
            continue
        if UNVERIFIED in line:
            continue
        line = SOURCE_REF.sub("", line)
        if is_table_row(line):
            cells = split_row(line)
            if drop is None:
                drop = {i for i, cell in enumerate(cells) if cell.lower() in DROP_COLUMNS}
                if is_separator(cells):
                    drop = None
            if drop:
                cells = [cell for i, cell in enumerate(cells) if i not in drop]
            line = join_row(cells)
        else:
            drop = None
        out.append(line)
    # схлопнуть пустые строки
    result, blank = [], True
    for line in out:
        if not line.strip():
            if not blank:
                result.append("")
            blank = True
        else:
            result.append(line)
            blank = False
    while result and not result[-1]:
        result.pop()
    return result


def prompt_text(text):
    return "\n".join(prompt_lines(text))


def demote(text):
    """Заголовки на уровень ниже (## -> ###), чтобы часть легла под заголовок раздела пакета."""
    return "\n".join("#" + line if HEADING.match(line) else line for line in text.split("\n"))


def size_of(text):
    return len(text.encode("utf-8"))
