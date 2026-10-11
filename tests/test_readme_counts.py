# -*- coding: utf-8 -*-
"""scripts/readme-counts.py: счётчики README по манифесту и строки новых направлений."""

import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = importlib.util.spec_from_file_location("readme_counts",
                                              os.path.join(ROOT, "scripts", "readme-counts.py"))
counts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(counts)
HSPEC = importlib.util.spec_from_file_location("hygiene", os.path.join(ROOT, "scripts", "hygiene.py"))
hygiene = importlib.util.module_from_spec(HSPEC)
HSPEC.loader.exec_module(hygiene)

README = """# t

| Направление | Что покрывает | Правил | Терминов |
|---|---|---|---|
| `core` | ядро — не зависит от конфигурации | 1 | 12 |
| `bp` | 1С:Бухгалтерия | открыто | — |

Текст после таблицы.
ловится только человеком; таких сейчас 1 из 2, и это видно.
"""


def track(code, title, state, rules, terms):
    return {"код": code, "название": title, "статус": state, "правил": rules, "терминов": terms}


MANIFEST = {
    "правил": 7,
    "ловятся_только_человеком": ["a", "b", "c"],
    "направления": [
        track("bp", "1С:Бухгалтерия", "ведётся", 2, 0),
        track("core", "Ядро", "ведётся", 5, 12),
        track("maerp", "maERP | своя", "открыто", 0, 0),
    ],
}


class ReadmeCounts(unittest.TestCase):

    def test_rewrite(self):
        out = counts.rewrite(README, MANIFEST)
        self.assertIn("| `core` | ядро — не зависит от конфигурации | 5 | 12 |", out)
        self.assertIn("| `bp` | 1С:Бухгалтерия | 2 | — |", out)
        # новое направление — строкой сразу после таблицы, «|» в названии не ломает таблицу
        self.assertIn("| `bp` | 1С:Бухгалтерия | 2 | — |\n| `maerp` | maERP / своя | открыто | — |\n\nТекст", out)
        self.assertIn("таких сейчас 3 из 7", out)

    def test_idempotent(self):
        once = counts.rewrite(README, MANIFEST)
        self.assertEqual(once, counts.rewrite(once, MANIFEST))

    def test_hygiene_accepts_result(self):
        """Итог читается hygiene.check_readme без находок — зеркало разбора строки."""
        import json
        import tempfile
        out = counts.rewrite(README, MANIFEST)
        tmp = tempfile.mkdtemp(prefix="tiny1c-readme-")
        saved = hygiene.MANIFEST_FILE, hygiene.README_FILE
        try:
            hygiene.MANIFEST_FILE = os.path.join(tmp, "manifest.json")
            hygiene.README_FILE = os.path.join(tmp, "README.md")
            with open(hygiene.MANIFEST_FILE, "w", encoding="utf-8") as handle:
                json.dump(MANIFEST, handle, ensure_ascii=False)
            with open(hygiene.README_FILE, "w", encoding="utf-8") as handle:
                handle.write(out)
            findings = []
            hygiene.check_readme(findings)
            self.assertEqual(findings, [])
        finally:
            hygiene.MANIFEST_FILE, hygiene.README_FILE = saved


if __name__ == "__main__":
    unittest.main()
