#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Прогон проверок исполняемых инструментов tiny1C на фикстурах.

Гоняет tests/ (unittest, только stdlib): where_is на синтетической выгрузке
fixtures/dump-mini с golden-ответами tests/golden/*.json, границы каталога
выгрузки и число инструментов сервера без флага и с --tools offline.

Использование:
  scripts/tools-check.py                          прогнать (1 при падении)
  TINY1C_UPDATE_GOLDEN=1 scripts/tools-check.py   пересобрать golden и прогнать;
                                                  diff golden смотреть глазами
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"), top_level_dir=ROOT)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        return 1
    print("Инструменты: проверок %d, все прошли." % result.testsRun)
    return 0


if __name__ == "__main__":
    sys.exit(main())
