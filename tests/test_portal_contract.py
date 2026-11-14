# -*- coding: utf-8 -*-
"""Договорённость с порталом TinyCIO.

Зачем этот тест. Набор tiny1C используют не только люди с плагином: портал TinyCIO
(сервис agent-service) и раннер ИИ-агентов на Windows читают его своим кодом -
по этим путям, ключам манифеста, именам инструментов и словарям. У портала есть
зеркала: словари категорий, серьёзности, платформ, источников и проверок, парсер
фронтматтера, список обязательных полей, имя обязательной проверки защиты main
(`intake`) и префикс веток `intake/`. Если набор сузит словарь, переименует файл
или ключ, портал молча начнёт отклонять черновики или не найдёт нужное.

Что делать, если тест упал при ОСОЗНАННОЙ смене. Сначала меняется портал (его
зеркала и выкат), потом этот набор, и только затем - зафиксированные ниже списки.
Расширять словари можно свободно (тест требует лишь, чтобы прежние значения
остались); сужать, переименовывать и добавлять обязательные поля правила - только
парой с порталом. Менять тест первым, чтобы он стал зелёным, нельзя.

Рецепты («как сделать», каталог `tracks/<направление>/guides/`) портал знает с выката
этапа 2: вид источника `практика`, обязательные поля рецепта, разделы шаблона
`tracks/_GUIDE_TEMPLATE.md`, ключ манифеста `рецепты` и инструменты `lookup_guide`/`get_guide`.

Навыки помощника (`tracks/<код>/skills/*.md`, инструменты `list_skills` и `get_skill`) читает сервис
ai1c-service портала и показывает бухгалтеру в списке «От TinyCIO»: имена ключей ответов, ключи шапки
`нужно` и `запуск`, виды параметров и потолки зафиксированы ниже. Сужать их и менять имена - сначала
портал; расширять можно (тест требует лишь, чтобы прежнее осталось).
"""

import importlib.util
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "mcp", "server.py")

SPEC = importlib.util.spec_from_file_location("tiny1c_manifest_contract",
                                              os.path.join(ROOT, "scripts", "manifest.py"))
manifest_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manifest_module)

# Зафиксировано: портал знает именно эти значения.
CATEGORIES = ["запросы", "модули", "формы-xml", "метаданные", "макеты", "процесс", "архитектура",
              "интерфейс", "данные", "интеграция", "дополнительные-отчеты-и-обработки", "расширения"]
SEVERITIES = ["критично", "важно", "справка"]
PLATFORMS = ["8.3", "8.5"]
SOURCES = ["ошибка", "измерение", "эксперимент", "образец", "решение", "документация",
           "практика"]
CHECKS = ["lint", "checkconfig", "checkconfig-ext", "smoke-forms", "smoke-samples", "smoke-print",
          "fixtures", "refcheck", "xml-audit", "manual"]
RULE_REQUIRED_MAX = ["id", "направление", "категория", "серьёзность", "платформы", "заголовок",
                     "ключи", "источник", "check"]
GUIDE_REQUIRED_MAX = ["id", "направление", "категория", "платформы", "заголовок", "источник",
                      "задача", "ключи", "check"]
TEMPLATE_SECTIONS = ["Симптом", "Причина", "Правило", "Как проверить", "История"]
GUIDE_TEMPLATE_SECTIONS = ["Шаги", "Проверка результата", "Где ломается"]
TOOL_NAMES = {"list_tracks", "lookup_rule", "get_rule", "lookup_guide", "get_guide",
              "rules_by_category", "rules_for_object", "checklist", "glossary_lookup", "where_is"}
TRACK_KEYS = ["код", "название", "вид", "конфигурации", "правила"]
INSTRUCTION_TOOL_NAMES = ["match_config", "get_instructions", "get_instructions_file", "get_cheats",
                          "list_skills", "get_skill"]
SKILL_REQUIRED_MAX = ["имя", "заголовок", "когда", "источник"]
SKILL_HEADER_FIXED = ["имя", "заголовок", "когда", "источник", "нужно", "запуск"]
SKILL_LIST_KEYS = ["name", "title", "when", "needs", "run", "size", "sha"]
SKILL_RUN_KEYS = ["text", "params"]
SKILL_PARAM_KEYS = ["key", "label", "kind", "required"]
SKILL_PARAM_KINDS = ["text", "inn", "period"]


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class PortalContract(unittest.TestCase):

    def test_paths_the_portal_reads_exist(self):
        for parts in (("mcp", "server.py"), ("scripts", "where-is-index.py"),
                      ("tracks", "_TEMPLATE.md"), ("tracks", "_GUIDE_TEMPLATE.md"),
                      ("manifest.json",)):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, *parts)), "/".join(parts))

    def test_template_sections(self):
        template = read("tracks", "_TEMPLATE.md")
        for section in TEMPLATE_SECTIONS:
            self.assertIn("\n## %s\n" % section, template, section)

    def test_guide_template_sections(self):
        template = read("tracks", "_GUIDE_TEMPLATE.md")
        for section in GUIDE_TEMPLATE_SECTIONS:
            self.assertIn("\n## %s\n" % section, template, section)
        keys = [line.split(":", 1)[0] for line in template.split("\n---", 1)[0].splitlines()[1:]
                if ":" in line]
        self.assertLess(keys.index("заголовок"), keys.index("источник"))
        self.assertEqual(keys.index("заголовок") + 1, keys.index("источник"))
        for field in GUIDE_REQUIRED_MAX:
            self.assertIn(field, keys)

    def test_manifest_keys(self):
        manifest = json.loads(read("manifest.json"))
        for key in ("направления", "правила", "инструменты", "рецепты"):
            self.assertIn(key, manifest)
        for track in manifest["направления"]:
            for key in TRACK_KEYS:
                self.assertIn(key, track, track.get("код"))
        for rule in manifest["правила"]:
            self.assertIn("id", rule)
            self.assertIn("файл", rule)
            self.assertTrue(rule["файл"].startswith("tracks/%s/rules/" % rule["направление"]),
                            rule["id"])
            self.assertTrue(os.path.isfile(os.path.join(ROOT, rule["файл"])), rule["id"])
        for tool in manifest["инструменты"]:
            self.assertIn("id", tool)
        self.assertEqual(manifest["рецептов"], len(manifest["рецепты"]))
        for guide in manifest["рецепты"]:
            self.assertIn("id", guide)
            self.assertIn("файл", guide)
            self.assertTrue(guide["файл"].startswith("tracks/%s/guides/" % guide["направление"]),
                            guide["id"])
            self.assertTrue(os.path.isfile(os.path.join(ROOT, guide["файл"])), guide["id"])

    def test_server_exposes_the_ten_tools(self):
        request = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
        done = subprocess.run([sys.executable, SERVER, "--tools", "offline"],
                              input=request.encode("utf-8"), stdout=subprocess.PIPE, timeout=60,
                              check=True, cwd=ROOT)
        names = {tool["name"] for tool in json.loads(done.stdout.decode("utf-8"))["result"]["tools"]}
        self.assertEqual(TOOL_NAMES, names)

    def test_instructions_group_has_skill_tools(self):
        request = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
        done = subprocess.run([sys.executable, SERVER, "--tools", "instructions"],
                              input=request.encode("utf-8"), stdout=subprocess.PIPE, timeout=60,
                              check=True, cwd=ROOT)
        names = [tool["name"] for tool in json.loads(done.stdout.decode("utf-8"))["result"]["tools"]]
        self.assertEqual(15, len(names))
        self.assertEqual(INSTRUCTION_TOOL_NAMES, names[-6:])

    def test_skill_contract(self):
        for field in SKILL_HEADER_FIXED:
            self.assertIn(field, manifest_module.SKILL_REQUIRED + manifest_module.SKILL_OPTIONAL, field)
        self.assertEqual(set(SKILL_REQUIRED_MAX), set(manifest_module.SKILL_REQUIRED),
                         "новое обязательное поле шапки навыка - сначала портал")
        self.assertEqual(SKILL_RUN_KEYS, manifest_module.SKILL_RUN_KEYS)
        self.assertEqual(set(SKILL_PARAM_KEYS),
                         set(manifest_module.SKILL_PARAM_REQUIRED + manifest_module.SKILL_PARAM_OPTIONAL))
        self.assertTrue(set(SKILL_PARAM_KINDS) <= set(manifest_module.SKILL_PARAM_KINDS))
        self.assertGreaterEqual(manifest_module.SKILL_RUN_PARAMS, 4)
        self.assertGreaterEqual(manifest_module.SKILL_RUN_TEXT_LIMIT, 300)
        self.assertEqual(["access", "caps"], sorted(manifest_module.SKILL_NEEDS_KEYS))

    def test_skill_answers_keep_their_keys(self):
        sys.path.insert(0, os.path.join(ROOT, "mcp"))
        try:
            import snapshot
            instructions = importlib.import_module("instructions")
        finally:
            sys.path.pop(0)
        snap = snapshot.load(ROOT)
        listing = instructions.tool_list_skills(snap, {"track": "bp"})
        self.assertEqual(["revision", "skills"], sorted(listing))
        self.assertTrue(listing["skills"])
        for item in listing["skills"]:
            self.assertEqual(sorted(SKILL_LIST_KEYS), sorted(item), item.get("name"))
            self.assertEqual(["access", "caps"], sorted(item["needs"]))
            if item["run"] is not None:
                self.assertEqual(sorted(SKILL_RUN_KEYS), sorted(item["run"]))
                for param in item["run"]["params"]:
                    self.assertEqual(sorted(SKILL_PARAM_KEYS), sorted(param))
        got = instructions.tool_get_skill(snap, {"track": "bp", "name": listing["skills"][0]["name"]})
        self.assertTrue({"name", "text", "sha"} <= set(got))
        self.assertIn("ошибка", instructions.tool_get_skill(snap, {"track": "bp", "name": "нет-такого"}))

    def test_dictionaries_only_grow(self):
        for name, fixed in (("CATEGORIES", CATEGORIES), ("SEVERITIES", SEVERITIES),
                            ("PLATFORMS", PLATFORMS), ("SOURCES", SOURCES), ("CHECKS", CHECKS)):
            current = getattr(manifest_module, name)
            self.assertTrue(set(fixed) <= set(current),
                            "%s потерял значения: %s" % (name, sorted(set(fixed) - set(current))))

    def test_required_fields_do_not_grow(self):
        extra = set(manifest_module.RULE_REQUIRED) - set(RULE_REQUIRED_MAX)
        self.assertEqual(set(), extra, "новое обязательное поле правила - сначала портал")

    def test_guide_required_fields_do_not_grow(self):
        extra = set(manifest_module.GUIDE_REQUIRED) - set(GUIDE_REQUIRED_MAX)
        self.assertEqual(set(), extra, "новое обязательное поле рецепта - сначала портал")
        self.assertEqual(set(GUIDE_REQUIRED_MAX), set(manifest_module.GUIDE_REQUIRED))

    def test_intake_workflow_names(self):
        text = read(".github", "workflows", "intake.yml")
        self.assertRegex(text, r"(?m)^jobs:\n  intake:\s*$")
        self.assertIn("intake/*", text)
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        # check-run на fixup-коммите: вызов с -f name=intake вне комментариев
        self.assertRegex(code, r"check-runs[^\n]*\n(?:[^\n]*\n)?[^\n]*-f name=intake\b")


if __name__ == "__main__":
    unittest.main()
