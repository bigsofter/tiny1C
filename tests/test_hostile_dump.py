# -*- coding: utf-8 -*-
"""Недоверенная выгрузка клиента: разбор не должен взрываться ни по памяти, ни по времени.

Опасные случаи гоняются в отдельном процессе с таймаутом: на уязвимом коде они
не падают, а висят или съедают память, и без таймаута зависла бы вся проверка.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE = os.path.join(ROOT, "fixtures", "dump-mini")
HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses" '
        'xmlns:v8="http://v8.1c.ru/8.1/data/core" '
        'xmlns:xr="http://v8.1c.ru/8.3/xcf/readable" version="2.16">\n')

PROBE = textwrap.dedent("""
    import json, resource, sys, time
    sys.path.insert(0, sys.argv[1])
    from tools import dump
    started = time.time()
    index = dump.load_index(sys.argv[2])
    print(json.dumps({"секунд": time.time() - started,
                      "подсистем": len(index.subsystems),
                      "предупреждения": index.warnings,
                      "синонимы": {key: obj["синоним"] for key, obj in index.objects.items()},
                      "maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},
                     ensure_ascii=False))
""")


def probe(dump_dir, timeout=20):
    """Построить индекс в отдельном процессе; упасть по таймауту, а не зависнуть."""
    done = subprocess.run([sys.executable, "-c", PROBE, os.path.join(ROOT, "mcp"), dump_dir],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                          check=True)
    return json.loads(done.stdout.decode("utf-8"))


def laughs(levels=8):
    """Вложенные сущности: каждая раскрывается в 10 копий предыдущей (10^levels)."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<!DOCTYPE MetaDataObject [',
             '  <!ENTITY l0 "ха-ха-ха-ха-ха-ха-ха-ха">']
    for level in range(1, levels + 1):
        lines.append('  <!ENTITY l%d "%s">' % (level, ("&l%d;" % (level - 1)) * 10))
    lines.append("]>")
    body = HEAD.split("\n", 1)[1]
    body += ('\t<Document uuid="00000000-0000-4000-8000-000000000999">\n\t\t<Properties>\n'
             '\t\t\t<Name>ЗаявкаНаРемонт</Name>\n\t\t\t<Synonym><v8:item><v8:lang>ru</v8:lang>'
             '<v8:content>&l%d;</v8:content></v8:item></Synonym>\n\t\t</Properties>\n'
             '\t</Document>\n</MetaDataObject>\n' % levels)
    return "\n".join(lines) + "\n" + body


def subsystem_xml(name, children):
    kids = "".join("\t\t\t<Subsystem>%s</Subsystem>\n" % item for item in children)
    return (HEAD + '\t<Subsystem uuid="00000000-0000-4000-8000-000000000998">\n\t\t<Properties>\n'
            '\t\t\t<Name>%s</Name>\n\t\t\t<IncludeInCommandInterface>true'
            '</IncludeInCommandInterface>\n\t\t\t<Content/>\n\t\t</Properties>\n'
            '\t\t<ChildObjects>\n%s\t\t</ChildObjects>\n\t</Subsystem>\n</MetaDataObject>\n'
            % (name, kids))


class HostileDump(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tiny1c-")
        self.dump = os.path.join(self.tmp, "dump")
        shutil.copytree(FIXTURE, self.dump)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write(self, rel, text):
        path = os.path.join(self.dump, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def add_top_subsystem(self, name):
        path = os.path.join(self.dump, "Configuration.xml")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        text = text.replace("\t\t</ChildObjects>",
                            "\t\t\t<Subsystem>%s</Subsystem>\n\t\t</ChildObjects>" % name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_billion_laughs_is_rejected(self):
        self.write("Documents/ЗаявкаНаРемонт.xml", laughs())
        self.write("Subsystems/Склад.xml", laughs())
        result = probe(self.dump)
        warnings = result["предупреждения"]
        self.assertTrue(any("Documents/ЗаявкаНаРемонт.xml" in item and "DTD" in item
                            for item in warnings), warnings)
        self.assertTrue(any("Subsystems/Склад.xml" in item and "DTD" in item
                            for item in warnings), warnings)
        self.assertEqual("", result["синонимы"]["Document.ЗаявкаНаРемонт"])
        self.assertLess(result["maxrss"], 300 * 1024 * 1024)  # байты на macOS, КБ на Linux

    def test_oversized_file_is_not_read(self):
        from tools import dump  # noqa: E402  (путь добавлен в test_where_is)
        path = os.path.join(self.dump, "Documents", "ЗаявкаНаРемонт.xml")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("<!-- %s -->\n" % ("x" * 20000))
        saved = dump.MAX_FILE_BYTES
        dump.MAX_FILE_BYTES = 10000
        try:
            dump._CACHE.clear()
            index = dump.load_index(self.dump)
        finally:
            dump.MAX_FILE_BYTES = saved
            dump._CACHE.clear()
        self.assertTrue(any("Documents/ЗаявкаНаРемонт.xml" in item and "больше" in item
                            for item in index.warnings), index.warnings)
        self.assertEqual("", index.objects["Document.ЗаявкаНаРемонт"]["синоним"])

    def test_duplicate_children_do_not_explode(self):
        # 17 уровней, на каждом дочерняя указана трижды: без защиты это 3^16 обходов.
        parts = ["Subsystems"]
        self.add_top_subsystem("Узел")
        for _level in range(17):
            self.write("/".join(parts + ["Узел.xml"]), subsystem_xml("Узел", ["Узел"] * 3))
            parts += ["Узел", "Subsystems"]
        started = time.time()
        result = probe(self.dump, timeout=20)
        self.assertLess(time.time() - started, 5)
        self.assertLess(result["секунд"], 1)
        self.assertTrue(any("дважды" in item for item in result["предупреждения"]))

    @unittest.skipIf(not hasattr(os, "symlink"), "нет символических ссылок")
    def test_symlink_loop_of_subsystems(self):
        # Subsystems/Петля/Subsystems -> .. : Петля видит саму себя дочерней, трижды.
        self.add_top_subsystem("Петля")
        self.write("Subsystems/Петля.xml", subsystem_xml("Петля", ["Петля"] * 3))
        os.makedirs(os.path.join(self.dump, "Subsystems", "Петля"))
        os.symlink("..", os.path.join(self.dump, "Subsystems", "Петля", "Subsystems"))
        result = probe(self.dump, timeout=20)
        self.assertLess(result["секунд"], 1)
        self.assertTrue(any("петля" in item for item in result["предупреждения"]),
                        result["предупреждения"])


if __name__ == "__main__":
    unittest.main()
