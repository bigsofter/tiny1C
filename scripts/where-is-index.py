#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Индекс «где найти» по всей выгрузке одним JSON — формат where_is_index_v1.

`where_is` отвечает на один запрос и держит индекс выгрузки в памяти процесса.
Агенту, у которого нет ни MCP, ни доступа к выгрузке (Консультант в хабе
TinyCIO), нужен тот же ответ заранее — по ВСЕМ объектам и разделам сразу.
Скрипт запускается там, где лежит выгрузка базы клиента (NAS), и печатает
индекс в stdout; дальше его кладут в agent-service
(`POST /internal/agents/metadata-dumps`, `format: "where_is_index_v1"`).

Состав индекса — компактная проекция карточек `where_is`:
  объекты:  полное имя, имя, синоним, навигационная ссылка, размещения
            (путь раздела, чем открыть, группа панели, видимость по ролям,
            видно ли в командном интерфейсе), права, примечание;
  разделы:  путь, видимость, подразделы, состав с командами открытия;
  глоссарий: термины набора, чьи объекты есть в этой выгрузке (поиск по
            термину — второй ярус `where_is`).
Поиск по индексу на стороне agent-service — зеркало правил `where_is`
(services/agent-service/internal/service/whereis.go): правишь одну сторону —
правь вторую.

Использование:
  scripts/where-is-index.py <каталог выгрузки> [--направление unf] > index.json
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "mcp"))

from tools import dump  # noqa: E402

FORMAT = "where_is_index_v1"


def visibility(view):
    """Видимость без поля «источник»: агенту важно кому, а не откуда известно."""
    if not view:
        return None
    return {key: view[key] for key in ("по_умолчанию", "роли_видят", "роли_скрыто") if key in view}


def opener_visibility(placement):
    opener = placement["открыть_командой"]
    if not opener:
        return None
    for card in placement["команды"]:
        if card["команда_метаданных"] == opener["команда_метаданных"]:
            return visibility(card.get("видимость"))
    return None


def compact_object(index, full):
    card = index.describe(full, "")
    places = []
    for item in card["размещения"]:
        opener = item["открыть_командой"]
        places.append({
            "путь": item["путь"],
            "подсистема": item["подсистема"],
            "видно": item["в_командном_интерфейсе"],
            "команда": opener["команда"] if opener else None,
            "группа": opener["группа"] if opener else None,
            "видимость_раздела": visibility(item["видимость_раздела"]),
            "видимость_команды": opener_visibility(item),
        })
    out = {
        "полное_имя": card["полное_имя"],
        "имя_метаданных": card["имя_метаданных"],
        "имя": index.objects[full]["имя"],
        "синоним": card["синоним"],
        "ссылка": card["навигационная_ссылка"],
        "размещения": places,
    }
    if card.get("права"):
        out["права"] = card["права"]
    for key in ("примечание", "оговорка"):
        if card.get(key):
            out[key] = card[key]
    if card.get("стандартные_команды") is False:
        out["стандартные_команды"] = False
    return out


def compact_section(index, key):
    card = index.describe_section(key, "")
    return {
        "подсистема": card["подсистема"],
        "имя": index.subsystems[key]["имя"],
        "путь": card["путь"],
        "видно": card["в_командном_интерфейсе"],
        "видимость": visibility(card["видимость_раздела"]),
        "подразделы": card["подразделы"],
        "состав": [{"полное_имя": item["полное_имя"], "синоним": item["синоним"],
                    "команда": item["команда"], "группа": item["группа"]}
                   for item in card["состав"]],
        "состав_всего": card["состав_всего"],
    }


def glossary(index, manifest, track):
    """Термины набора, у которых хотя бы один объект есть в выгрузке."""
    out = []
    for entry in manifest.get("направления", []):
        if track and entry.get("код") != track:
            continue
        for term in entry.get("глоссарий", []):
            found = []
            for target in term.get("объекты", []):
                full = dump.normalize_full_name(target)
                key = index.by_fold.get(dump.fold(full)) if full else None
                if key and dump.russian_name(key) not in found:
                    found.append(dump.russian_name(key))
            if found:
                out.append({"термин": term.get("термин", ""),
                            "синонимы": list(term.get("синонимы", [])),
                            "направление": entry.get("код", ""),
                            "объекты": found})
    return out


def build(root, track=None, manifest=None):
    index = dump.load_index(root)
    if manifest is None:
        manifest = dump.load_manifest()
    objects = sorted(index.objects, key=dump.russian_name)
    return {
        "format": FORMAT,
        "конфигурация": {"имя": index.config_name, "синоним": index.config_synonym},
        "объекты": [compact_object(index, full) for full in objects],
        "разделы": [compact_section(index, key) for key in sorted(index.subsystems)],
        "глоссарий": glossary(index, manifest, track),
        "внимание": dump.NOTE_DATA,
        "предупреждения": list(index.warnings),
    }


def main(argv):
    args = list(argv)
    track = None
    if "--направление" in args:
        at = args.index("--направление")
        if at + 1 >= len(args):
            print("--направление: нужен код направления", file=sys.stderr)
            return 2
        track = args[at + 1]
        del args[at:at + 2]
    if len(args) != 1:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    root = os.path.realpath(args[0])
    if not os.path.isfile(os.path.join(root, "Configuration.xml")):
        print("нет Configuration.xml в %s — это не выгрузка конфигурации" % root, file=sys.stderr)
        return 2
    json.dump(build(root, track), sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
