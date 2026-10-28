# -*- coding: utf-8 -*-
"""Снимок набора: манифест + корень дерева, из которого читаются тела записей.

Stdio-сервер живёт с одним снимком всю сессию (корень — репозиторий рядом с
кодом). Сетевой сервис (mcp/httpd.py) держит текущий снимок и подменяет его
целиком, когда из git приходит новая исправная ревизия знаний: обработчики
инструментов получают снимок аргументом и ничего не читают из глобального
корня, поэтому запрос, начавшийся на старой ревизии, на ней и закончится.

Snapshot — словарь манифеста (чтобы весь старый код `manifest["правила"]` и
кэш индексов по id(manifest) работали как раньше) с атрибутами:
  root      корень дерева набора, относительно него лежат «файл» записей;
  digest    короткий хеш manifest.json (версия набора в serverInfo);
  revision  ревизия знаний: sha коммита или «встроенная» (копия из образа/клона).
"""

import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBEDDED = "встроенная"


class Snapshot(dict):
    root = ROOT
    digest = "0"
    revision = EMBEDDED
    loaded_at = ""


def digest_of(raw):
    """Хеш содержимого манифеста; переводы строк не влияют (git на Windows их меняет)."""
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()[:12]


def load(root=None, revision=EMBEDDED, manifest_text=None):
    """Снимок по manifest.json в корне `root` (или по готовому тексту манифеста)."""
    root = ROOT if root is None else os.path.abspath(root)
    if manifest_text is None:
        with open(os.path.join(root, "manifest.json"), "rb") as handle:
            raw = handle.read()
    else:
        raw = manifest_text.encode("utf-8")
    snapshot = Snapshot(json.loads(raw.decode("utf-8")))
    snapshot.root = root
    snapshot.digest = digest_of(raw)
    snapshot.revision = revision
    return snapshot


def root_of(manifest):
    """Корень дерева для снимка; для голого словаря манифеста — репозиторий рядом с кодом."""
    return getattr(manifest, "root", ROOT)


def read_text(manifest, rel):
    """Текст файла набора по относительному пути из манифеста (UTF-8)."""
    with open(os.path.join(root_of(manifest), rel), encoding="utf-8") as handle:
        return handle.read()
