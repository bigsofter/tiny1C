# -*- coding: utf-8 -*-
"""Навыки помощника: сборка в манифест (scripts/manifest.py) и инструменты list_skills / get_skill.

Навык лежит в `tracks/<код>/skills/<имя>.md`: шапка (имя, заголовок, когда, источник; необязательно
нужно и запуск - JSON) и тело. Текст навыка помощник считает инструкцией, поэтому манифест отвергает всё
сомнительное: нет шапки, лишний ключ, ссылка, слишком большой размер, битый «запуск».
Инструменты проверяются на синтетической фикстуре знаний и на настоящих семенах bp.
"""

import json
import os
import shutil
import tempfile
import unittest

from tests import knowledge_fixture as kf

ROOT = kf.ROOT
builder = kf.load_module("tiny1c_manifest_skills", "scripts", "manifest.py")
instructions = kf.load_module("tiny1c_instructions_skills", "mcp", "instructions.py")
server = kf.load_module("tiny1c_server_skills", "mcp", "server.py")
GOLDEN = os.path.join(ROOT, "tests", "golden")
UPDATE = os.environ.get("TINY1C_UPDATE_GOLDEN") == "1"

GOOD_RUN = {"text": "Покажи отчёт за {period}",
            "params": [{"key": "period", "label": "Период", "kind": "period", "required": True}]}


def skill_text(name="demo", title="Демо", when="просят демо", extra="", body="# Демо\n\nТекст.\n",
               source="образец: проверка"):
    head = "---\nимя: %s\nзаголовок: %s\nкогда: %s\nисточник: %s\n%s---\n" % (name, title, when, source, extra)
    return head + body


def golden(test, name, result):
    path = os.path.join(GOLDEN, "skills_%s.json" % name)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if UPDATE:
        os.makedirs(GOLDEN, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    with open(path, encoding="utf-8") as handle:
        test.assertEqual(handle.read(), text, "golden %s разошёлся; TINY1C_UPDATE_GOLDEN=1 пересоберёт" % name)


class Build(unittest.TestCase):
    """collect_skills / check_skill_sets на временном дереве."""

    def tree(self, files, extra=None):
        """Дерево с направлением bp: files = {имя файла навыка: текст}; extra = {код: {имя: текст}}."""
        tmp = tempfile.mkdtemp(prefix="tiny1c-skills-")
        self.addCleanup(shutil.rmtree, tmp, True)
        groups = {"bp": files}
        groups.update(extra or {})
        for code, items in groups.items():
            directory = os.path.join(tmp, "tracks", code)
            os.makedirs(os.path.join(directory, "skills"))
            with open(os.path.join(directory, "track.md"), "w", encoding="utf-8") as handle:
                handle.write("---\nкод: %s\nназвание: %s\nвид: %s\nплатформы: [8.3]\nстатус: ведётся\n---\n"
                             % (code, code, "ядро" if code == "core" else "типовая"))
            for name, text in items.items():
                with open(os.path.join(directory, "skills", name), "w", encoding="utf-8") as handle:
                    handle.write(text)
        return tmp

    def build(self, files, extra=None):
        built, errors = builder.collect(root=self.tree(files, extra))
        return built, errors

    def errors(self, files, extra=None):
        return self.build(files, extra)[1]

    def assertError(self, errors, marker):
        self.assertTrue(any(marker in error for error in errors), (marker, errors))

    def test_good_skill_is_indexed(self):
        run = json.dumps(GOOD_RUN, ensure_ascii=False)
        text = skill_text(extra='нужно: {"caps":["print"],"access":["write320"]}\nзапуск: %s\n' % run)
        built, errors = self.build({"demo.md": text})
        self.assertEqual([], errors)
        skill = built["направления"][0]["инструкции"]["навыки"][0]
        self.assertEqual("demo", skill["имя"])
        self.assertEqual("Демо", skill["заголовок"])
        self.assertEqual({"caps": ["print"], "access": ["write320"]}, skill["нужно"])
        self.assertEqual({"text": "Покажи отчёт за {period}",
                          "params": [{"key": "period", "label": "Период", "kind": "period", "required": True}]},
                         skill["запуск"])
        self.assertEqual("tracks/bp/skills/demo.md", skill["файл"])
        self.assertEqual(12, len(skill["sha"]))
        self.assertEqual(len("# Демо\n\nТекст.".encode("utf-8")), skill["размер"])

    def test_defaults_without_optional_header(self):
        built, errors = self.build({"demo.md": skill_text()})
        self.assertEqual([], errors)
        skill = built["направления"][0]["инструкции"]["навыки"][0]
        self.assertEqual({"caps": [], "access": []}, skill["нужно"])
        self.assertIsNone(skill["запуск"])

    def test_run_without_params_is_fine_and_required_defaults_to_false(self):
        run = {"text": "Покажи, что умеешь", "params": []}
        self.assertEqual([], self.errors({"demo.md": skill_text(extra="запуск: %s\n" % json.dumps(run, ensure_ascii=False))}))
        run = {"text": "Отчёт за {p}", "params": [{"key": "p", "label": "Период", "kind": "period"}]}
        built, errors = self.build({"demo.md": skill_text(extra="запуск: %s\n" % json.dumps(run, ensure_ascii=False))})
        self.assertEqual([], errors)
        self.assertIs(False, built["направления"][0]["инструкции"]["навыки"][0]["запуск"]["params"][0]["required"])

    def test_readme_in_skills_dir_is_not_a_skill(self):
        built, errors = self.build({"demo.md": skill_text(), "README.md": "происхождение\n"})
        self.assertEqual([], errors)
        self.assertEqual(["demo"], [s["имя"] for s in built["направления"][0]["инструкции"]["навыки"]])

    def test_no_header_is_refused(self):
        self.assertError(self.errors({"demo.md": "# Просто текст\n"}), "нет шапки")

    def test_missing_and_unknown_fields(self):
        text = "---\nимя: demo\nзаголовок: Демо\nисточник: образец: x\n---\nтекст\n"
        self.assertError(self.errors({"demo.md": text}), "нет поля «когда»")
        self.assertError(self.errors({"demo.md": skill_text(extra="лишнее: 1\n")}), "неизвестное поле шапки «лишнее»")
        self.assertError(self.errors({"demo.md": skill_text(source="мнение: кто-то сказал")}), "источник")

    def test_name_rules(self):
        self.assertError(self.errors({"demo.md": skill_text(name="other")}), "не совпадает с именем файла")
        self.assertError(self.errors({"Demo.md": skill_text(name="Demo")}), "не по формату")
        self.assertError(self.errors({"a.md": skill_text(name="a")}), "не по формату")

    def test_length_ceilings(self):
        self.assertError(self.errors({"demo.md": skill_text(title="я" * 61)}), "заголовок")
        self.assertError(self.errors({"demo.md": skill_text(when="я" * 201)}), "«когда»")
        self.assertEqual([], self.errors({"demo.md": skill_text(title="я" * 60, when="я" * 200)}))

    def test_body_size_ceiling(self):
        big = "я" * (builder.SKILL_BODY_LIMIT // 2 + 1)
        self.assertError(self.errors({"demo.md": skill_text(body=big)}), "тело навыка")
        ok = "я" * (builder.SKILL_BODY_LIMIT // 2)
        self.assertEqual([], self.errors({"demo.md": skill_text(body=ok)}))

    def test_empty_body_is_refused(self):
        self.assertError(self.errors({"demo.md": skill_text(body="\n\n")}), "пустое тело")

    def test_links_are_refused_everywhere(self):
        for body in ("Смотри http://example.invalid/x\n", "Смотри https://example.invalid/x\n", "Сайт www.example.invalid\n"):
            self.assertError(self.errors({"demo.md": skill_text(body=body)}), "ссылка", )
        self.assertError(self.errors({"demo.md": skill_text(when="смотри http://example.invalid")}), "ссылка")

    def test_control_characters_are_refused(self):
        self.assertError(self.errors({"demo.md": skill_text(body="текст\x07\n")}), "управляющие символы")

    def test_needs_validation(self):
        for extra, marker in (("нужно: [1]\n", "объектом"),
                              ("нужно: не json\n", "не JSON"),
                              ('нужно: {"ext":"5.5.0"}\n', "неизвестный ключ"),
                              ('нужно: {"caps":"print"}\n', "нужно.caps"),
                              ('нужно: {"caps":["Print Form"]}\n', "нужно.caps"),
                              ('нужно: {"access":[%s]}\n' % ",".join('"a%d"' % i for i in range(9)), "нужно.access")):
            self.assertError(self.errors({"demo.md": skill_text(extra=extra)}), marker)

    def run_errors(self, run, raw=None):
        value = raw if raw is not None else json.dumps(run, ensure_ascii=False)
        return self.errors({"demo.md": skill_text(extra="запуск: %s\n" % value)})

    def test_run_not_json_or_not_object(self):
        self.assertError(self.run_errors(None, raw="{text: нет}"), "не JSON")
        self.assertError(self.run_errors(None, raw='["a"]'), "объектом")
        self.assertError(self.run_errors({"params": []}), "запуск.text")
        self.assertError(self.run_errors(dict(GOOD_RUN, лишний=1)), "неизвестный ключ")

    def test_run_text_limits(self):
        long = {"text": "я" * 301, "params": []}
        self.assertError(self.run_errors(long), "потолок 300")
        self.assertEqual([], self.run_errors({"text": "я" * 300, "params": []}))
        for text in ("Смотри [тут](x)", "Сделай **жирно**", "Строка `код`", "# заголовок", "Сделай <b>это</b>",
                     "одна | две", "Открой http://example.invalid", "Открой www.example.invalid"):
            self.assertTrue(self.run_errors({"text": text, "params": []}), text)
        self.assertError(self.run_errors({"text": "первая\\nвторая", "params": []}), "разметкой")

    def test_run_params_limits(self):
        params = [{"key": "p%d" % i, "label": "П%d" % i, "kind": "text"} for i in range(5)]
        text = " ".join("{p%d}" % i for i in range(5))
        self.assertError(self.run_errors({"text": text, "params": params}), "5 параметров")
        self.assertEqual([], self.run_errors({"text": " ".join("{p%d}" % i for i in range(4)), "params": params[:4]}))

    def test_run_param_validation(self):
        base = {"key": "period", "label": "Период", "kind": "period"}
        for change, marker in (({"kind": "date"}, "вид «date»"),
                               ({"key": "Period"}, "не по формату"),
                               ({"label": ""}, "без поля «label»"),
                               ({"label": "Смотри `тут`"}, "без ссылок и разметки"),
                               ({"required": "да"}, "required"),
                               ({"hint": "x"}, "неизвестное поле «hint»")):
            run = {"text": "Отчёт за {%s}" % base["key"] if change.get("key") is None else "Отчёт за {%s}" % change["key"],
                   "params": [dict(base, **change)]}
            self.assertError(self.run_errors(run), marker)
        self.assertError(self.run_errors({"text": "за {a}", "params": ["a"]}), "не объект")
        twin = {"text": "за {a}", "params": [{"key": "a", "label": "А", "kind": "text"}] * 2}
        self.assertError(self.run_errors(twin), "повторяется")

    def test_run_placeholders_match_params(self):
        self.assertError(self.run_errors({"text": "за {нет}", "params": []}), "такого параметра нет")
        self.assertError(self.run_errors({"text": "за {x}", "params": [{"key": "x", "label": "Х", "kind": "text"},
                                                                      {"key": "y", "label": "У", "kind": "text"}]}),
                         "не подставлен")
        self.assertError(self.run_errors({"text": "за { x", "params": []}), "фигурная скобка")

    def test_duplicate_with_core_and_overrides(self):
        files = {"reports.md": skill_text(name="reports")}
        core = {"core": {"reports.md": skill_text(name="reports")}}
        self.assertError(self.errors(files, core), "уже есть в core")
        # одноимённые навыки разных направлений без «расширяет» - не конфликт
        other = {"unf": {"demo.md": skill_text()}}
        self.assertEqual([], self.errors({"demo.md": skill_text()}, other))

    def test_count_and_total_ceilings(self):
        many = {"s%02d.md" % i: skill_text(name="s%02d" % i) for i in range(21)}
        self.assertError(self.errors(many), "навыков 21, потолок 20")
        self.assertEqual([], self.errors({"s%02d.md" % i: skill_text(name="s%02d" % i) for i in range(20)}))
        body = "я" * (builder.SKILL_BODY_LIMIT // 2 - 100)
        heavy = {"h%d.md" % i: skill_text(name="h%d" % i, body=body) for i in range(7)}
        self.assertError(self.errors(heavy), "навыки")
        # потолок считается и по набору с core
        core = {"core": {"c%d.md" % i: skill_text(name="c%d" % i, body=body) for i in range(4)}}
        mixed = {"h%d.md" % i: skill_text(name="h%d" % i, body=body) for i in range(3)}
        self.assertError(self.errors(mixed, core), "с core")

    def test_skills_only_track_still_gets_a_pack(self):
        built, errors = self.build({"demo.md": skill_text()})
        self.assertEqual([], errors)
        pack = built["направления"][0]["инструкции"]
        self.assertIsNone(pack["профиль"])
        self.assertEqual(0, built["инструкций"])  # считаются только пакеты с профилем

    def test_manifest_changes_with_skill_text(self):
        tree = self.tree({"demo.md": skill_text()})
        first, _ = builder.collect(root=tree)
        with open(os.path.join(tree, "tracks", "bp", "skills", "demo.md"), "a", encoding="utf-8") as handle:
            handle.write("Ещё строка.\n")
        second, _ = builder.collect(root=tree)
        one = first["направления"][0]["инструкции"]["навыки"][0]
        two = second["направления"][0]["инструкции"]["навыки"][0]
        self.assertNotEqual(one["sha"], two["sha"])
        self.assertGreater(two["размер"], one["размер"])


class Tools(unittest.TestCase):
    """list_skills / get_skill на фикстуре знаний (core, ut, ka с «расширяет: ut», unf без пакета)."""

    @classmethod
    def setUpClass(cls):
        cls.tree = kf.fixture_copy(cls)
        cls.snap = kf.snapshot_of(cls.tree, revision="abc123")

    def listing(self, **args):
        return instructions.tool_list_skills(self.snap, args)

    def names(self, track):
        return [item["name"] for item in self.listing(track=track)["skills"]]

    def test_list_for_direction_includes_core_first(self):
        result = self.listing(track="ut")
        self.assertEqual("abc123", result["revision"])
        self.assertEqual(["queries-howto", "orders"], [item["name"] for item in result["skills"]])
        self.assertEqual(["name", "needs", "run", "sha", "size", "title", "when"],
                         sorted(result["skills"][0]))

    def test_list_item_shape(self):
        core, orders = self.listing(track="ut")["skills"]
        self.assertIsNone(core["run"])
        self.assertEqual({"caps": [], "access": []}, core["needs"])
        self.assertEqual("Заказы клиентов за период", orders["title"])
        self.assertEqual({"caps": ["print"], "access": ["write320"]}, orders["needs"])
        self.assertEqual("Покажи заказы клиентов за {period} по менеджеру {manager}", orders["run"]["text"])
        self.assertEqual([{"key": "period", "label": "Период", "kind": "period", "required": True},
                          {"key": "manager", "label": "Менеджер", "kind": "text", "required": False}],
                         orders["run"]["params"])
        self.assertEqual(12, len(orders["sha"]))
        self.assertGreater(orders["size"], 0)

    def test_extends_chain_and_override(self):
        # ka расширяет ut: core, потом база, потом своё; одноимённый навык ka закрывает навык ut
        result = self.listing(track="ka")
        self.assertEqual(["queries-howto", "ka-only", "orders"], [i["name"] for i in result["skills"]])
        orders = [item for item in result["skills"] if item["name"] == "orders"][0]
        self.assertEqual("Заказы клиентов в КА", orders["title"])
        self.assertIsNone(orders["run"])

    def test_core_and_direction_without_pack(self):
        self.assertEqual(["queries-howto"], self.names("core"))
        self.assertEqual(["queries-howto"], self.names("unf"))

    def test_list_errors(self):
        for args in ({}, {"track": ""}, {"track": "нет"}):
            result = self.listing(**args)
            self.assertIn("ошибка", result, args)
            self.assertIn("ut", result["ошибка"])
        self.assertNotIn("skills", self.listing(track="нет"))

    def test_get_skill_returns_body_without_header_and_unverified_lines(self):
        result = instructions.tool_get_skill(self.snap, {"track": "ut", "name": "orders"})
        self.assertEqual({"name", "text", "sha", "unverified_dropped"}, set(result))
        self.assertEqual("orders", result["name"])
        self.assertTrue(result["text"].startswith("# Заказы клиентов\n"))
        self.assertIn("Итоговая строка навыка.", result["text"])
        self.assertNotIn("[проверить]", result["text"])
        self.assertNotIn("никто не подтвердил", result["text"])
        self.assertNotIn("---", result["text"])
        self.assertNotIn("запуск:", result["text"])
        self.assertEqual(1, result["unverified_dropped"])
        listed = [i for i in self.listing(track="ut")["skills"] if i["name"] == "orders"][0]
        self.assertEqual(listed["sha"], result["sha"])

    def test_get_skill_without_unverified_has_exact_keys(self):
        result = instructions.tool_get_skill(self.snap, {"track": "ut", "name": "queries-howto"})
        self.assertEqual({"name", "text", "sha"}, set(result))
        self.assertIn("виртуальную таблицу", result["text"])

    def test_get_skill_follows_override_and_core(self):
        mine = instructions.tool_get_skill(self.snap, {"track": "ka", "name": "orders"})
        self.assertIn("этапы оформления", mine["text"])
        base = instructions.tool_get_skill(self.snap, {"track": "ut", "name": "orders"})
        self.assertNotEqual(base["sha"], mine["sha"])
        self.assertIn("виртуальную", instructions.tool_get_skill(self.snap, {"track": "ka", "name": "queries-howto"})["text"])

    def test_get_skill_errors(self):
        for args in ({"track": "ut"}, {"track": "ut", "name": "нет"}, {"track": "нет", "name": "orders"},
                     {"name": "orders"}, {"track": "unf", "name": "orders"}, {"track": "ut", "name": "ka-only"}):
            result = instructions.tool_get_skill(self.snap, args)
            self.assertIn("ошибка", result, args)
            self.assertNotIn("text", result)

    def test_golden_list_and_get(self):
        golden(self, "list_ka", self.listing(track="ka"))
        golden(self, "get_orders_ut", instructions.tool_get_skill(self.snap, {"track": "ut", "name": "orders"}))

    def test_tools_through_server(self):
        tools, handlers = server.enabled_tools(self.snap, {"instructions"})
        names = [tool["name"] for tool in tools]
        self.assertEqual(["list_skills", "get_skill"], names[-2:])
        for tool in tools[-2:]:
            self.assertTrue(tool["annotations"]["readOnlyHint"], tool["name"])
            self.assertEqual(["track"], tool["inputSchema"]["required"][:1])
        answer = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": "list_skills", "arguments": {"track": "ut"}}},
                               self.snap, tools, handlers)
        self.assertNotIn("isError", answer)
        self.assertEqual(2, len(json.loads(answer["content"][0]["text"])["skills"]))
        answer = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                "params": {"name": "get_skill", "arguments": {"track": "ut", "name": "orders"}}},
                               self.snap, tools, handlers)
        self.assertEqual("orders", json.loads(answer["content"][0]["text"])["name"])


class Seeds(unittest.TestCase):
    """Настоящие навыки репозитория: семена bp проходят проверку и укладываются в потолки."""

    @classmethod
    def setUpClass(cls):
        import snapshot
        cls.snap = snapshot.load(ROOT)

    def test_repository_builds_without_errors(self):
        built, errors = builder.collect()
        self.assertEqual([], errors)
        bp = [t for t in built["направления"] if t["код"] == "bp"][0]["инструкции"]["навыки"]
        self.assertEqual(["print-forms", "reports"], [s["имя"] for s in bp])

    def test_seeds_listed_for_bp(self):
        result = instructions.tool_list_skills(self.snap, {"track": "bp"})
        by_name = {item["name"]: item for item in result["skills"]}
        self.assertIn("reports", by_name)
        self.assertIn("print-forms", by_name)
        self.assertEqual({"caps": ["print"], "access": []}, by_name["print-forms"]["needs"])
        self.assertEqual({"caps": [], "access": []}, by_name["reports"]["needs"])
        for item in by_name.values():
            self.assertLessEqual(item["size"], 3 * 1024, item["name"])
            self.assertLessEqual(len(item["when"]), builder.SKILL_WHEN_LIMIT)

    def test_seed_texts_are_gettable_and_say_the_key_things(self):
        reports = instructions.tool_get_skill(self.snap, {"track": "bp", "name": "reports"})
        self.assertIn("run_report", reports["text"])
        self.assertIn("Оборотно-сальдовая ведомость", reports["text"])
        self.assertIn("show_route", reports["text"])
        self.assertNotIn("[проверить]", reports["text"])
        prints = instructions.tool_get_skill(self.snap, {"track": "bp", "name": "print-forms"})
        self.assertIn("print_form", prints["text"])
        self.assertIn("по памяти", prints["text"])
        self.assertIn("счёт-фактура не выписана", prints["text"])
        for result in (reports, prints):
            self.assertNotIn("http", result["text"])

    def test_bp_where_is_forbids_form_numbers_from_memory(self):
        with open(os.path.join(ROOT, "tracks", "bp", "where_is.md"), encoding="utf-8") as handle:
            text = handle.read()
        row = [line for line in text.splitlines() if line.startswith("| Печать документа")][0]
        self.assertIn("номера и названия бланков по памяти не называй", row)


if __name__ == "__main__":
    unittest.main()
