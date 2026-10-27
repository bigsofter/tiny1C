# -*- coding: utf-8 -*-
"""Группа инструментов «instructions»: пакет инструкций по конфигурации для ИИ-помощника в базе 1С.

Помощник (на стороне портала TinyCIO — «Татьяна») подключается к базе, видит
Метаданные.Имя, версию и поставщика конфигурации, и ему нужно ОДНИМ вызовом
получить всё, что набор знает про эту конфигурацию: где что в меню, объекты,
особенности, типовые вопросы, чипы-подсказки и шпаргалки языка запросов, чтобы
положить это в системный промпт. Отсюда три инструмента:

  match_config           факты базы -> направление набора (по profile.json);
  get_instructions       пакет направления для промпта с учётом «расширяет» (ka/erp поверх ut):
                         профиль, where_is и notes в сжатом виде (mcp/packtext.py), чипы;
  get_instructions_file  один файл пакета целиком (objects.md, faq.md, where_is.md, notes.md) — по запросу;
  get_cheats             шпаргалки платформы (tracks/core/cheats/*.md).

Формат пакета и profile.json — README, «Пакет инструкций по конфигурации».
Группа включается флагом `--tools instructions`; сетевой сервис включает её сам.
"""

import json
import re

import packtext
import snapshot as snap

PROMPT_FILES = ("where_is.md", "notes.md")
FILE_TOOLS = ("objects.md", "faq.md", "where_is.md", "notes.md")

INSTRUCTION_TOOLS = [
    {
        "name": "match_config",
        "description": "Определить направление набора по фактам базы 1С: Метаданные.Имя "
                       "конфигурации (name), версия (version), поставщик (vendor), синоним "
                       "(synonym). Сравнивает с паспортами profile.json направлений: точное "
                       "имя, затем синоним по регулярному выражению; отдельно говорит, "
                       "совпал ли поставщик и не ниже ли версия минимальной. Ответ — "
                       "направление (track) для get_instructions и список кандидатов.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Метаданные.Имя, например БухгалтерияПредприятия"},
                "version": {"type": "string", "description": "версия конфигурации, например 3.0.165.20"},
                "vendor": {"type": "string", "description": "поставщик, например Фирма \"1С\""},
                "synonym": {"type": "string", "description": "синоним конфигурации, если имя неизвестно"},
            },
        },
        "annotations": {"title": "Определить конфигурацию", "readOnlyHint": True,
                        "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_instructions",
        "description": "Пакет инструкций по конфигурации для системного промпта одним вызовом: "
                       "профиль, «где это в 1С» и особенности в сжатом виде (без неподтверждённых "
                       "строк, подробных разделов и колонок статуса), чипы; если направление "
                       "расширяет другое (ka/erp поверх ut) — сначала части базового, потом "
                       "добавки. Поле «текст» — готовый markdown; «части» — то же по файлам. "
                       "include_core=true добавляет шпаргалки платформы (как get_cheats). "
                       "Карта объектов и типовые вопросы целиком — get_instructions_file. "
                       "Направление — из match_config.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track": {"type": "string", "description": "код направления, например bp"},
                "include_core": {"type": "boolean",
                                 "description": "добавить шпаргалки core (по умолчанию false)"},
            },
            "required": ["track"],
        },
        "annotations": {"title": "Пакет инструкций по конфигурации", "readOnlyHint": True,
                        "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_instructions_file",
        "description": "Один файл пакета инструкций целиком, как справочник: objects.md (карта "
                       "объектов: документ, роль, чем закрывается), faq.md (типовые вопросы и "
                       "ответы-маршруты), where_is.md или notes.md без сжатия. Для разовых "
                       "вопросов, когда сжатого пакета из get_instructions мало. Строки с "
                       "пометкой [проверить] — неподтверждённые, их не выдавать как факт.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track": {"type": "string", "description": "код направления, например bp"},
                "file": {"type": "string", "description": "objects.md | faq.md | where_is.md | notes.md"},
                "with_base": {"type": "boolean",
                              "description": "добавить тот же файл базового направления (по умолчанию true)"},
            },
            "required": ["track", "file"],
        },
        "annotations": {"title": "Файл пакета инструкций", "readOnlyHint": True,
                        "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "get_cheats",
        "description": "Шпаргалки платформы (язык запросов, регистры накопления, бухгалтерии, "
                       "расчёта) из tracks/core/cheats — общие для всех конфигураций, кладутся "
                       "в промпт целиком. Поле «текст» — готовый markdown, «шпаргалки» — по файлам.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "track": {"type": "string", "description": "направление со шпаргалками (по умолчанию core)"},
            },
        },
        "annotations": {"title": "Шпаргалки платформы", "readOnlyHint": True,
                        "destructiveHint": False, "openWorldHint": False},
    },
]


def tracks_with_packs(manifest):
    return {track["код"]: track for track in manifest["направления"]
            if track.get("инструкции")}


def version_tuple(text):
    parts = []
    for item in str(text or "").strip().split("."):
        if not item.isdigit():
            return None
        parts.append(int(item))
    return tuple(parts) if parts else None


def norm_vendor(text):
    """Поставщик без кавычек, регистра и пробелов: «Фирма "1С"» == «фирма 1с»."""
    return re.sub(r"[\s\"'«»“”„]+", "", str(text or "")).lower()


def tool_match_config(manifest, args):
    name = str(args.get("name") or "").strip()
    synonym = str(args.get("synonym") or "").strip()
    version = str(args.get("version") or "").strip()
    vendor = str(args.get("vendor") or "").strip()
    if not name and not synonym:
        return {"ошибка": "нужно имя конфигурации (name, Метаданные.Имя) или synonym"}
    candidates = []
    for code, track in sorted(tracks_with_packs(manifest).items()):
        profile = track["инструкции"].get("профиль")
        if not profile:
            continue
        how = None
        if name and name.lower() in [item.lower() for item in profile.get("имена", [])]:
            how = "имя"
        elif profile.get("синоним_re"):
            pattern = re.compile(profile["синоним_re"], re.I)
            if (synonym and pattern.search(synonym)) or (name and pattern.search(name)):
                how = "синоним"
        if how is None:
            continue
        card = {"направление": code, "название": track["название"], "совпадение": how,
                "семейство": profile.get("семейство"), "тема": profile.get("тема"),
                "расширяет": profile.get("расширяет")}
        vendors = profile.get("поставщики") or []
        if vendors and vendor:
            card["поставщик_совпадает"] = norm_vendor(vendor) in {norm_vendor(v) for v in vendors}
        else:
            card["поставщик_совпадает"] = None
        minimum = profile.get("мин_версия")
        if minimum and version:
            have, need = version_tuple(version), version_tuple(minimum)
            card["версия_поддерживается"] = (None if have is None or need is None
                                             else have >= need)
            card["мин_версия"] = minimum
        else:
            card["версия_поддерживается"] = None
        candidates.append(card)
    rank = {"имя": 0, "синоним": 1}
    candidates.sort(key=lambda card: (rank[card["совпадение"]],
                                      card["поставщик_совпадает"] is False,
                                      card["направление"]))
    if not candidates:
        return {"направление": None, "кандидаты": [],
                "причина": "ни один profile.json не знает такое имя или синоним; "
                           "направления с пакетом: %s"
                           % ", ".join(sorted(code for code, track in tracks_with_packs(manifest).items()
                                              if track["инструкции"].get("профиль")))}
    best = candidates[0]
    return {"направление": best["направление"], "совпадение": best["совпадение"],
            "поставщик_совпадает": best["поставщик_совпадает"],
            "версия_поддерживается": best["версия_поддерживается"],
            "кандидаты": candidates}


def extends_chain(manifest, code):
    """Цепочка направлений от базового к запрошенному: [ut, ka] для ka -> ut."""
    packs = tracks_with_packs(manifest)
    chain, current = [], code
    while current and current in packs and current not in chain and len(chain) < 4:
        chain.append(current)
        current = packs[current]["инструкции"].get("расширяет")
    chain.reverse()
    return chain


def read_chips(manifest, codes):
    """Чипы направлений по порядку (core — общие — первым); чипы с «проверить» не отдаются."""
    packs = tracks_with_packs(manifest)
    chips = []
    for code in codes:
        track = packs.get(code)
        if not track:
            continue
        for item in track["инструкции"]["файлы"]:
            if item["имя"] != "chips.json":
                continue
            for chip in json.loads(snap.read_text(manifest, item["файл"])):
                if chip.get("проверить") is True:
                    continue
                chips.append(dict(chip, **{"направление": code}))
    return chips


def read_parts(manifest, chain, names=PROMPT_FILES, compact=True):
    """Части пакета по цепочке: файлы базового направления, потом добавки."""
    packs = tracks_with_packs(manifest)
    parts = []
    for code in chain:
        for item in packs[code]["инструкции"]["файлы"]:
            if item["имя"] not in names:
                continue
            text = snap.read_text(manifest, item["файл"])
            text = packtext.prompt_text(text) if compact else text.rstrip("\n")
            text = packtext.demote(text)
            parts.append({"направление": code, "имя": item["имя"],
                          "раздел": PACK_TITLES.get(item["имя"], item["имя"]),
                          "sha": item["sha"], "текст": text})
    return parts


def render_profile(track):
    """Профиль одной строкой на факт — то, что помощнику нужно знать о конфигурации."""
    profile = track["инструкции"]["профиль"]
    lines = ["## Конфигурация", "",
             "- Конфигурация: %s (направление набора `%s`, семейство `%s`); тема: %s."
             % (track["название"], track["код"], profile.get("семейство"), profile.get("тема"))]
    if profile.get("имена"):
        lines.append("- Имена конфигурации (Метаданные.Имя): %s." % ", ".join(profile["имена"]))
    if profile.get("мин_версия"):
        lines.append("- Инструкции рассчитаны на версии от %s." % profile["мин_версия"])
    flags = profile.get("признаки") or {}
    have = [name for name, on in flags.items() if on]
    absent = [name for name, on in flags.items() if on is False]
    if have or absent:
        lines.append("- Регистры: есть %s%s." % (", ".join(have) or "—",
                                                   ("; нет " + ", ".join(absent)) if absent else ""))
    if profile.get("план_счетов"):
        lines.append("- План счетов: %s%s." % (profile["план_счетов"],
                                                ("; виды субконто: " + profile["виды_субконто"])
                                                if profile.get("виды_субконто") else ""))
    if profile.get("без_кода"):
        lines.append("- Настраивается без программирования: %s." % ", ".join(profile["без_кода"]))
    return "\n".join(lines)


PACK_TITLES = {"where_is.md": "Где это в 1С", "objects.md": "Объекты и документы",
               "notes.md": "Особенности конфигурации", "faq.md": "Типовые вопросы"}


def cheats_of(manifest, code):
    packs = tracks_with_packs(manifest)
    track = packs.get(code)
    if not track:
        return []
    found = []
    for item in track["инструкции"].get("шпаргалки", []):
        found.append({"имя": item["имя"], "заголовок": item["заголовок"], "sha": item["sha"],
                      "текст": snap.read_text(manifest, item["файл"]).rstrip("\n")})
    return found


def render_parts(title, parts, chain):
    lines = ["# %s" % title, ""]
    for part in parts:
        heading = part["раздел"]
        if len(chain) > 1 and part["направление"] != chain[-1]:
            heading += " (общее, %s)" % part["направление"]
        elif len(chain) > 1:
            heading += " (добавки %s)" % part["направление"]
        lines += ["## " + heading, "", part["текст"], ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def render_cheats(cheats):
    lines = []
    for cheat in cheats:
        lines += ["## " + cheat["заголовок"], "", cheat["текст"], ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def pack_track(manifest, args):
    """(направление с пакетом, None) или (None, ответ-ошибка)."""
    code = str(args.get("track") or "").strip()
    packs = tracks_with_packs(manifest)
    with_profile = sorted(c for c, t in packs.items() if t["инструкции"].get("профиль"))
    if not code:
        return None, {"ошибка": "нужен код направления (track), например bp; есть: %s"
                                % ", ".join(with_profile)}
    track = packs.get(code)
    if track is None or not track["инструкции"].get("профиль"):
        return None, {"ошибка": "у направления «%s» нет пакета инструкций; есть: %s"
                                % (code, ", ".join(with_profile))}
    return track, None


def tool_get_instructions(manifest, args):
    track, error = pack_track(manifest, args)
    if error:
        return error
    code = track["код"]
    chain = extends_chain(manifest, code)
    parts = read_parts(manifest, chain)
    chips = read_chips(manifest, ["core"] + chain if "core" not in chain else chain)
    title = "Инструкции по конфигурации: %s" % track["название"]
    text = render_parts(title, parts, chain).replace("# %s\n\n" % title,
                                                      "# %s\n\n%s\n\n" % (title, render_profile(track)), 1)
    result = {
        "направление": code,
        "название": track["название"],
        "ревизия": getattr(manifest, "revision", snap.EMBEDDED),
        "версия": getattr(manifest, "digest", "0"),
        "профиль": track["инструкции"]["профиль"],
        "расширяет": chain[:-1],
        "части": parts,
        "чипы": chips,
        "файлы_по_запросу": sorted({item["имя"] for c in chain
                                     for item in tracks_with_packs(manifest)[c]["инструкции"]["файлы"]
                                     if item["имя"] in FILE_TOOLS and item["имя"] not in PROMPT_FILES}),
    }
    if args.get("include_core") is True:
        cheats = cheats_of(manifest, "core")
        result["шпаргалки"] = cheats
        if cheats:
            text += "\n# Шпаргалки платформы\n\n" + render_cheats(cheats)
    result["текст"] = text
    result["размер"] = len(text.encode("utf-8"))
    return result


def tool_get_instructions_file(manifest, args):
    track, error = pack_track(manifest, args)
    if error:
        return error
    name = str(args.get("file") or "").strip()
    if name not in FILE_TOOLS:
        return {"ошибка": "file — один из: %s" % ", ".join(FILE_TOOLS)}
    chain = extends_chain(manifest, track["код"])
    if args.get("with_base") is False:
        chain = chain[-1:]
    parts = read_parts(manifest, chain, names=(name,), compact=False)
    if not parts:
        return {"ошибка": "у направления «%s» нет файла %s" % (track["код"], name)}
    title = "%s: %s" % (PACK_TITLES.get(name, name), track["название"])
    text = render_parts(title, parts, chain)
    return {"направление": track["код"], "файл": name,
            "ревизия": getattr(manifest, "revision", snap.EMBEDDED),
            "расширяет": chain[:-1], "части": parts, "текст": text,
            "размер": len(text.encode("utf-8")),
            "примечание": "строки с пометкой [проверить] не подтверждены — не выдавать как факт"
            if packtext.UNVERIFIED in text else None}


def tool_get_cheats(manifest, args):
    code = str(args.get("track") or "core").strip()
    cheats = cheats_of(manifest, code)
    if not cheats:
        return {"ошибка": "у направления «%s» нет шпаргалок (tracks/%s/cheats/*.md)" % (code, code)}
    text = render_cheats(cheats)
    return {"направление": code, "ревизия": getattr(manifest, "revision", snap.EMBEDDED),
            "версия": getattr(manifest, "digest", "0"), "шпаргалки": cheats,
            "текст": text, "размер": len(text.encode("utf-8"))}


INSTRUCTION_HANDLERS = {
    "match_config": tool_match_config,
    "get_instructions": tool_get_instructions,
    "get_instructions_file": tool_get_instructions_file,
    "get_cheats": tool_get_cheats,
}
