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
     образец, решение, документация, практика (проверенный в деле порядок
     действий; ждёт этого вида и рецепт). Правило без своего источника в набор не
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
     проверку вида `fixtures` — инструмент без фикстуры не публикуется;
  8. рецепты `tracks/<код>/guides/how-NNN.md` — разделы «рецепты» (верх и у
     направления): id по формату how-001 и сквозной уникальности, непустая
     `задача`, источник/check по тем же правилам, `правила` — список id
     существующих правил;
  9. пакет инструкций по конфигурации `tracks/<код>/profile.json` + `where_is.md`,
     `objects.md`, `notes.md`, `faq.md`, `chips.json` и шпаргалки
     `tracks/<код>/cheats/*.md` — ключ «инструкции» у направления: профиль по
     схеме (см. PROFILE_* ниже), `расширяет` только на направление с пакетом,
     чипы — JSON-список записей с id/заголовок/текст; потолки: текст для
     промпта (profile + where_is + notes + chips после сжатия по mcp/packtext.py)
     не больше PROMPT_LIMIT, сырые файлы пакета — PACK_LIMIT, шпаргалки —
     CHEATS_LIMIT. Файл sources.md (источники S-n с URL) в пакет не входит.

Использование:
  scripts/manifest.py             собрать manifest.json
  scripts/manifest.py --проверить проверить без записи (1 при расхождениях)
  scripts/manifest.py --корень ДИР [--проверить]
                                  работать с другим деревом набора (сетевой сервис
                                  проверяет так свежую ревизию знаний своим кодом)
"""

import hashlib
import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACKS = os.path.join(ROOT, "tracks")
MANIFEST = os.path.join(ROOT, "manifest.json")

# Пакет инструкций по конфигурации (для ИИ-помощника, который работает в базе 1С).
PACK_FILES = ["where_is.md", "objects.md", "notes.md", "faq.md", "chips.json"]
PACK_TITLES = {"where_is.md": "Где это в 1С", "objects.md": "Объекты и документы",
               "notes.md": "Особенности конфигурации", "faq.md": "Типовые вопросы"}
CHEATS_DIR = "cheats"
PROMPT_FILES = ["where_is.md", "notes.md"]   # markdown-части, которые get_instructions кладёт в промпт
PROMPT_LIMIT = 24 * 1024        # байт текста для промпта на направление (профиль + where_is + notes + чипы, сжато)
PACK_LIMIT = 96 * 1024          # байт сырых файлов пакета направления (справочник с пометками)
CHEATS_LIMIT = 24 * 1024        # байт шпаргалок (они тоже идут в промпт целиком)
PROFILE_REQUIRED = ["семейство", "имена", "тема"]
PROFILE_OPTIONAL = ["синоним_re", "мин_версия", "поставщики", "признаки", "план_счетов",
                    "виды_субконто", "без_кода", "расширяет"]
PROFILE_FLAGS = ["бухгалтерия", "накопление", "расчёт"]
VERSION_RE = re.compile(r"^\d+(\.\d+){1,3}$")
FAMILY_RE = re.compile(r"^[a-z][a-z0-9-]*$")
CHIP_REQUIRED = ["id", "заголовок", "текст"]
CHIP_OPTIONAL = ["тема", "подсказка", "параметры", "проверить"]
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

CATEGORIES = ["запросы", "модули", "формы-xml", "метаданные", "макеты", "процесс",
              "архитектура", "интерфейс", "данные", "интеграция",
              "дополнительные-отчеты-и-обработки", "расширения"]
SEVERITIES = ["критично", "важно", "справка"]
PLATFORMS = ["8.3", "8.5"]
SOURCES = ["ошибка", "измерение", "эксперимент", "образец", "решение", "документация", "практика"]
CHECKS = ["lint", "checkconfig", "checkconfig-ext", "smoke-forms", "smoke-samples",
          "smoke-print", "fixtures", "refcheck", "xml-audit", "manual"]
RULE_REQUIRED = ["id", "направление", "категория", "серьёзность", "платформы",
                 "заголовок", "ключи", "источник", "check"]
GUIDE_REQUIRED = ["id", "направление", "категория", "платформы", "заголовок", "источник",
                  "задача", "ключи", "check"]
GUIDE_ID_RE = re.compile(r"^how-\d{3}$")
TRACK_REQUIRED = ["код", "название", "вид", "платформы", "статус"]
TRACK_KINDS = ["ядро", "с-нуля", "типовая", "собственная"]
TRACK_STATES = ["ведётся", "открыто"]

TOOLS_DIR = os.path.join(ROOT, "tools")
TOOL_REQUIRED = ["id", "группа", "инструмент", "сигнатура", "исполнение", "опасность",
                 "идея", "источник", "check", "статус", "правила"]
TOOL_GROUPS = ["introspection", "ops-copy", "debug", "ui", "help"]
TOOL_EXECUTION = ["offline", "agent-edt", "runner-copy", "runner-ro", "runner-ui"]
TOOL_DANGER = ["read", "write-copy", "exec-copy"]
TOOL_STATES = ["реализован", "карточка"]
# Копилефт-лицензии образца: аббревиатурой (AGPL-3.0, LGPL, GPLv3) или прописью.
LICENSE_COPYLEFT = re.compile(r"(?i)\b(A?GPL|LGPL)|GNU\s+(Affero\s+|Lesser\s+|Library\s+)?"
                              r"General\s+Public\s+License")


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


SYMPTOM_LIMIT = 700


def read_symptom(body):
    """Текст раздела «## Симптом» (пробелы схлопнуты, не длиннее SYMPTOM_LIMIT) или пустая строка.

    Для поиска lookup_rule: по дословному тексту ошибки правило находят чаще, чем
    по заголовку. Поле вычисляется из тела и во фронтматтер не пишется.
    """
    match = re.search(r"(?m)^## Симптом[ \t]*\n(.*?)(?=^## |\Z)", body, re.S)
    if not match:
        return ""
    return " ".join(match.group(1).split())[:SYMPTOM_LIMIT]


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


_packtext = None


def packtext():
    """mcp/packtext.py — правила сжатия текста пакета для промпта (общие с сервером)."""
    global _packtext
    if _packtext is None:
        spec = importlib.util.spec_from_file_location(
            "tiny1c_packtext", os.path.join(ROOT, "mcp", "packtext.py"))
        _packtext = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_packtext)
    return _packtext


def read_pack_text(path, rel, errors):
    """Текст файла пакета: UTF-8 без управляющих символов. None при ошибке."""
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        errors.append("%s: не читается как UTF-8 (%s)" % (rel, error))
        return None
    if CONTROL_RE.search(text):
        errors.append("%s: управляющие символы в тексте" % rel)
        return None
    return text.replace("\r\n", "\n")


def file_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def check_profile(profile, where, code, errors):
    """Схема profile.json: закрытый набор ключей, типы и форматы значений."""
    if not isinstance(profile, dict):
        errors.append("%s: profile.json должен быть объектом JSON" % where)
        return
    for key in PROFILE_REQUIRED:
        if key not in profile:
            errors.append("%s: нет поля «%s»" % (where, key))
    for key in profile:
        if key not in PROFILE_REQUIRED and key not in PROFILE_OPTIONAL:
            errors.append("%s: неизвестное поле «%s» (есть: %s)"
                          % (where, key, ", ".join(PROFILE_REQUIRED + PROFILE_OPTIONAL)))
    family = profile.get("семейство", "")
    if not isinstance(family, str) or not FAMILY_RE.match(family):
        errors.append("%s: «семейство» — латиница, цифры, дефис (например bp), а не «%s»"
                      % (where, family))
    names = profile.get("имена")
    if not isinstance(names, list) or not names \
            or not all(isinstance(item, str) and item.strip() for item in names):
        errors.append("%s: «имена» — непустой список строк (Метаданные.Имя конфигурации)" % where)
    else:
        for item in names:
            if re.search(r"\s", item):
                errors.append("%s: имя конфигурации «%s» с пробелом — это синоним, а не Имя"
                              % (where, item))
    topic = profile.get("тема")
    if not isinstance(topic, str) or not topic.strip():
        errors.append("%s: «тема» — непустая строка (учёт и налоги, торговля и склад…)" % where)
    synonym = profile.get("синоним_re")
    if synonym is not None:
        if not isinstance(synonym, str):
            errors.append("%s: «синоним_re» должен быть строкой" % where)
        else:
            try:
                re.compile(synonym)
            except re.error as error:
                errors.append("%s: «синоним_re» не компилируется: %s" % (where, error))
    version = profile.get("мин_версия")
    if version is not None and (not isinstance(version, str) or not VERSION_RE.match(version)):
        errors.append("%s: «мин_версия» вида 3.0.150, а не «%s»" % (where, version))
    for key in ("поставщики", "без_кода"):
        value = profile.get(key)
        if value is not None and (not isinstance(value, list)
                                  or not all(isinstance(item, str) and item.strip()
                                             for item in value)):
            errors.append("%s: «%s» — список строк" % (where, key))
    flags = profile.get("признаки")
    if flags is not None:
        if not isinstance(flags, dict) or not all(isinstance(v, bool) for v in flags.values()):
            errors.append("%s: «признаки» — объект с булевыми значениями" % where)
        else:
            for key in flags:
                if key not in PROFILE_FLAGS:
                    errors.append("%s: неизвестный признак «%s» (есть: %s)"
                                  % (where, key, ", ".join(PROFILE_FLAGS)))
    for key in ("план_счетов", "виды_субконто"):
        value = profile.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append("%s: «%s» — непустая строка" % (where, key))
    extends = profile.get("расширяет")
    if extends is not None:
        if not isinstance(extends, str) or not extends.strip():
            errors.append("%s: «расширяет» — код направления" % where)
        elif extends == code:
            errors.append("%s: направление не может расширять само себя" % where)


def check_chips(text, where, errors):
    """chips.json — список подсказок-чипов: id, заголовок, текст (+ необязательная тема)."""
    try:
        chips = json.loads(text)
    except ValueError as error:
        errors.append("%s: не JSON (%s)" % (where, error))
        return
    if not isinstance(chips, list):
        errors.append("%s: нужен список чипов" % where)
        return
    seen = set()
    for position, chip in enumerate(chips):
        if not isinstance(chip, dict):
            errors.append("%s: чип №%d не объект" % (where, position + 1))
            continue
        for key in CHIP_REQUIRED:
            if not isinstance(chip.get(key), str) or not chip[key].strip():
                errors.append("%s: чип №%d без поля «%s»" % (where, position + 1, key))
        for key in chip:
            if key not in CHIP_REQUIRED and key not in CHIP_OPTIONAL:
                errors.append("%s: чип №%d — неизвестное поле «%s» (есть: %s)"
                              % (where, position + 1, key, ", ".join(CHIP_REQUIRED + CHIP_OPTIONAL)))
        if "параметры" in chip and not isinstance(chip["параметры"], dict):
            errors.append("%s: чип №%d — «параметры» должны быть объектом" % (where, position + 1))
        if "проверить" in chip and not isinstance(chip["проверить"], bool):
            errors.append("%s: чип №%d — «проверить» true/false" % (where, position + 1))
        if chip.get("id") in seen:
            errors.append("%s: id чипа «%s» повторяется" % (where, chip.get("id")))
        seen.add(chip.get("id"))


def collect_pack(code, track_dir, errors):
    """Пакет инструкций направления: профиль, файлы пакета и шпаргалки. None, если ничего нет.

    Файлы пакета без profile.json — ошибка: без паспорта конфигурацию не узнать,
    а значит, пакет никому не достанется. Шпаргалки (`cheats/`) профиля не требуют.
    Ссылку «расширяет» проверяет вызывающий после сбора всех направлений.
    """
    profile, files, cheats, prompt_size = None, [], [], 0
    profile_path = os.path.join(track_dir, "profile.json")
    if os.path.exists(profile_path):
        where = "%s/profile.json" % code
        text = read_pack_text(profile_path, where, errors)
        if text is not None:
            try:
                profile = json.loads(text)
            except ValueError as error:
                errors.append("%s: не JSON (%s)" % (where, error))
                profile = None
            else:
                check_profile(profile, where, code, errors)
                if not isinstance(profile, dict):
                    profile = None
                else:
                    prompt_size += len(text.encode("utf-8"))
    for name in PACK_FILES:
        path = os.path.join(track_dir, name)
        if not os.path.exists(path):
            continue
        where = "%s/%s" % (code, name)
        text = read_pack_text(path, where, errors)
        if text is None:
            continue
        if name == "chips.json":
            check_chips(text, where, errors)
            prompt_size += len(text.encode("utf-8"))
        elif name in PROMPT_FILES:
            prompt_size += packtext().size_of(packtext().prompt_text(text))
        files.append({"имя": name, "файл": "tracks/%s/%s" % (code, name),
                      "sha": file_digest(text), "размер": len(text.encode("utf-8"))})
    orphans = [item["имя"] for item in files if item["имя"] not in ("objects.md", "chips.json")]
    if orphans and not os.path.exists(profile_path):
        # objects.md — ещё и карта объектов для программиста; chips.json у core — общие чипы.
        errors.append("%s: файлы пакета (%s) без profile.json — конфигурацию не определить"
                      % (code, ", ".join(orphans)))
    cheats_dir = os.path.join(track_dir, CHEATS_DIR)
    if os.path.isdir(cheats_dir):
        for name in sorted(os.listdir(cheats_dir)):
            if not name.endswith(".md") or name == "README.md":
                continue
            where = "%s/%s/%s" % (code, CHEATS_DIR, name)
            text = read_pack_text(os.path.join(cheats_dir, name), where, errors)
            if text is None:
                continue
            title = name[:-3]
            for line in text.splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            cheats.append({"имя": name[:-3], "заголовок": title,
                           "файл": "tracks/%s/%s/%s" % (code, CHEATS_DIR, name),
                           "sha": file_digest(text), "размер": len(text.encode("utf-8"))})
    if profile is None and not files and not cheats:
        return None
    size = sum(item["размер"] for item in files)
    cheats_size = sum(item["размер"] for item in cheats)
    if prompt_size > PROMPT_LIMIT:
        errors.append("%s: текст пакета для промпта %d байт больше потолка %d — сократить notes/where_is "
                      "или перенести подробности в разделы «(подробно)»" % (code, prompt_size, PROMPT_LIMIT))
    if size > PACK_LIMIT:
        errors.append("%s: файлы пакета %d байт больше потолка %d" % (code, size, PACK_LIMIT))
    if cheats_size > CHEATS_LIMIT:
        errors.append("%s: шпаргалки %d байт больше потолка %d" % (code, cheats_size, CHEATS_LIMIT))
    return {
        "профиль": profile,
        "расширяет": (profile or {}).get("расширяет"),
        "файлы": files,
        "шпаргалки": cheats,
        "размер": size,
        "размер_промпта": prompt_size,
        "размер_шпаргалок": cheats_size,
    }


def check_extends(tracks, errors):
    """«расширяет» ведёт на направление с профилем; цепочка без циклов и не длиннее трёх."""
    packs = {track["код"]: track.get("инструкции") for track in tracks}
    for track in tracks:
        pack = track.get("инструкции")
        if not pack or not pack.get("расширяет"):
            continue
        chain, code = [track["код"]], pack["расширяет"]
        while code:
            if code in chain:
                errors.append("%s/profile.json: цикл «расширяет»: %s" % (track["код"],
                                                                        " -> ".join(chain + [code])))
                break
            target = packs.get(code)
            if target is None or target.get("профиль") is None:
                errors.append("%s/profile.json: «расширяет» ведёт на «%s», а там нет пакета с profile.json"
                              % (track["код"], code))
                break
            chain.append(code)
            if len(chain) > 3:
                errors.append("%s/profile.json: цепочка «расширяет» длиннее трёх направлений"
                              % track["код"])
                break
            code = target.get("расширяет")


def collect_tools(rule_ids, errors, tools_dir=None):
    """Карточки инструментов tools/<группа>/<инструмент>.md (кроме _TEMPLATE.md)."""
    tools = []
    tools_dir = TOOLS_DIR if tools_dir is None else tools_dir
    root = os.path.dirname(tools_dir)
    if not os.path.isdir(tools_dir):
        return tools
    seen = set()
    for current, dirs, files in os.walk(tools_dir):
        dirs.sort()
        for name in sorted(files):
            if not name.endswith(".md") or name in ("_TEMPLATE.md", "README.md"):
                continue
            path = os.path.join(current, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
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
            elif LICENSE_COPYLEFT.search(idea) and "только идея" not in idea:
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


def collect_guides(code, track_dir, seen_ids, errors):
    """Рецепты tracks/<код>/guides/*.md (кроме README.md и _GUIDE_TEMPLATE.md).

    Ссылки «правила» проверяет вызывающий после сбора всех направлений.
    """
    guides = []
    guides_dir = os.path.join(track_dir, "guides")
    if not os.path.isdir(guides_dir):
        return guides
    for name in sorted(os.listdir(guides_dir)):
        if not name.endswith(".md") or name in ("README.md", "_GUIDE_TEMPLATE.md"):
            continue
        where = "%s/guides/%s" % (code, name)
        data, _ = read_document(os.path.join(guides_dir, name))
        if data is None:
            errors.append("%s: нет фронтматтера" % where)
            continue
        guide_id = data.get("id", "")
        if guide_id != name[:-3]:
            errors.append("%s: id «%s» не совпадает с именем файла" % (where, guide_id))
        if not isinstance(guide_id, str) or not GUIDE_ID_RE.match(guide_id):
            errors.append("%s: id «%s» не по формату «how-001»" % (where, guide_id))
        if guide_id in seen_ids:
            errors.append("%s: id «%s» уже занят в наборе" % (where, guide_id))
        seen_ids.add(guide_id)
        for field in GUIDE_REQUIRED:
            if field not in data:
                errors.append("%s: нет поля «%s»" % (where, field))
        if data.get("направление") != code:
            errors.append("%s: направление «%s» не совпадает с каталогом"
                          % (where, data.get("направление")))
        if data.get("категория") not in CATEGORIES:
            errors.append("%s: неизвестная категория «%s»" % (where, data.get("категория")))
        platforms = data.get("платформы", [])
        for platform in platforms if isinstance(platforms, list) else [platforms]:
            if platform not in PLATFORMS:
                errors.append("%s: неизвестная платформа «%s»" % (where, platform))
        task = data.get("задача", "")
        if not isinstance(task, str) or not task.strip():
            errors.append("%s: пустая «задача» — что получаем в итоге" % where)
        linked = data.get("правила", [])
        if not isinstance(linked, list):
            errors.append("%s: «правила» должны быть списком" % where)
            linked = []
        check_source(data, where, errors)
        checks = check_checks(data, where, errors)
        guide = dict(data)
        guide["правила"] = list(linked)
        guide["файл"] = "tracks/%s/guides/%s" % (code, name)
        guide["виды_проверок"] = sorted({entry.split(":", 1)[0] for entry in checks})
        guides.append(guide)
    return guides


def collect(root=None):
    """Разбор дерева tracks. Возвращает (манифест, список ошибок).

    `root` — корень набора; по умолчанию репозиторий, в котором лежит скрипт.
    Сетевой сервис передаёт сюда свежую ревизию знаний: проверяет её этим,
    своим кодом, а не скриптом из той ревизии.
    """
    tracks_dir = TRACKS if root is None else os.path.join(root, "tracks")
    root = ROOT if root is None else root
    errors, tracks, rules, guides = [], [], [], []
    seen_ids = set()
    if not os.path.isdir(tracks_dir):
        return None, ["%s: нет каталога tracks" % root]
    for code in sorted(os.listdir(tracks_dir)):
        track_dir = os.path.join(tracks_dir, code)
        if not os.path.isdir(track_dir) or code.startswith("_"):
            continue  # «_PACK_TEMPLATE» и подобные заготовки — не направления
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
                data, body = read_document(os.path.join(rules_dir, name))
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
                symptom = read_symptom(body)
                if symptom:
                    rule["симптом"] = symptom
                rule["файл"] = "tracks/%s/rules/%s" % (code, name)
                rule["виды_проверок"] = sorted({entry.split(":", 1)[0] for entry in checks})
                rules.append(rule)
                track_rules.append(rule_id)

        track_guides = collect_guides(code, track_dir, seen_ids, errors)
        guides.extend(track_guides)

        glossary = read_glossary(os.path.join(track_dir, "glossary.md"))
        entry = dict(passport)
        entry["правил"] = len(track_rules)
        entry["правила"] = track_rules
        entry["рецептов"] = len(track_guides)
        entry["рецепты"] = [guide["id"] for guide in track_guides]
        entry["терминов"] = len(glossary)
        entry["глоссарий"] = glossary
        entry["карта_объектов"] = ("tracks/%s/objects.md" % code
                                   if os.path.exists(os.path.join(track_dir, "objects.md"))
                                   else None)
        entry["инструкции"] = collect_pack(code, track_dir, errors)
        tracks.append(entry)
    check_extends(tracks, errors)

    by_object = {}
    for rule in rules:
        for obj in rule.get("объекты", []):
            by_object.setdefault(obj, []).append(rule["id"])
    for track in tracks:
        for term in track["глоссарий"]:
            for obj in term["объекты"]:
                by_object.setdefault(obj, [])

    rule_ids = {rule["id"] for rule in rules}
    for guide in guides:
        for rule_id in guide["правила"]:
            if rule_id not in rule_ids:
                errors.append("%s: правила «%s» в наборе нет" % (guide["файл"], rule_id))
    guides.sort(key=lambda guide: guide.get("id", ""))

    manual_only = [rule["id"] for rule in rules if rule["виды_проверок"] == ["manual"]]
    tools = collect_tools({rule["id"] for rule in rules}, errors,
                          tools_dir=None if root == ROOT else os.path.join(root, "tools"))
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
        "рецептов": len(guides),
        "рецепты": guides,
        "инструкций": sum(1 for track in tracks
                          if track["инструкции"] and track["инструкции"]["профиль"]),
    }
    return manifest, errors


def render(manifest):
    """Текст manifest.json: один и тот же для сборки, проверки и сетевого сервиса."""
    return json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def parse_root(argv):
    """--корень ДИР (или --root ДИР): другое дерево набора. None — своё."""
    for position, arg in enumerate(argv):
        if arg in ("--корень", "--root") and position + 1 < len(argv):
            return os.path.abspath(argv[position + 1])
        for prefix in ("--корень=", "--root="):
            if arg.startswith(prefix):
                return os.path.abspath(arg[len(prefix):])
    return None


def main():
    dry_run = "--проверить" in sys.argv[1:] or "--check" in sys.argv[1:]
    root = parse_root(sys.argv[1:])
    manifest_path = MANIFEST if root is None else os.path.join(root, "manifest.json")
    manifest, errors = collect(root)

    for error in errors:
        print("ОШИБКА: %s" % error)
    if manifest is None:
        return 1
    body = render(manifest)

    if dry_run:
        stale = True
        if os.path.exists(manifest_path):
            with open(manifest_path, encoding="utf-8") as handle:
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

    with open(manifest_path, "w", encoding="utf-8") as handle:
        handle.write(body)
    print("Записан manifest.json: направлений %d, правил %d, только человеком ловятся %d, "
          "инструментов %d, рецептов %d"
          % (manifest["направлений"], manifest["правил"],
             len(manifest["ловятся_только_человеком"]), manifest["инструментов"],
             manifest["рецептов"]))
    for track in manifest["направления"]:
        print("  %-11s %-42s правил %2d, терминов %2d"
              % (track["код"], track["название"], track["правил"], track["терминов"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
