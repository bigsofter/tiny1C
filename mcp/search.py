# -*- coding: utf-8 -*-
"""Поиск правил для lookup_rule: слова, словоформы, ранжирование по полям.

Только stdlib. Запрос и тексты приводятся к одному виду (регистр, е=ё,
пунктуация и скобки отброшены), режутся на слова, у русских слов отбрасывается
типичное окончание — «шапка», «шапки» и «поле», «поля», «полей» сходятся к одной основе.

Порядок важности полей: id (точное совпадение) > заголовок > ключи > симптом
(раздел «## Симптом», вычисляется манифестом) > тело правила. Правило попадает
в выдачу, если ВСЕ слова запроса нашлись в id, заголовке, ключах или симптоме.
Если таких нет, поиск идёт по полному тексту правил («найдено по тексту»), а при
длинном запросе — по части слов. Тела читаются с диска лениво, только на этом шаге.
"""

import re

ID_PREFIX = re.compile(r"^[a-z]{3,}(-\d*)?$")  # тема (bsl, forms) или тема с началом номера (bsl-0)
WORD = re.compile(r"[0-9a-zа-я]+")

STOPWORDS = {
    "и", "в", "во", "на", "не", "с", "со", "по", "к", "у", "о", "об", "от", "до", "за", "из",
    "для", "или", "при", "что", "как", "это", "то", "же", "ли", "а", "но", "бы",
}

# От длинных к коротким: срезается самое длинное подходящее окончание.
ENDINGS = sorted([
    "ыми", "ими", "ого", "его", "ому", "ему", "ами", "ями", "иях", "ях", "ах", "ов", "ев",
    "ей", "ой", "ий", "ый", "ая", "яя", "ое", "ее", "ые", "ие", "ую", "юю", "ом", "ем",
    "ам", "ям", "ых", "их", "ть", "ся", "ла", "ло", "ли", "а", "я", "о", "е", "ы", "и", "у", "ю", "ь", "й",
], key=len, reverse=True)

# Вес слова запроса, найденного в поле: заголовок важнее ключей, ключи — симптома, симптом — тела.
WEIGHTS = {"id": 10.0, "title": 8.0, "keys": 6.0, "symptom": 3.0, "body": 1.0}
PHRASE_BONUS = {"title": 20.0, "keys": 15.0, "symptom": 8.0, "body": 3.0}
PREFIX_FACTOR = 0.5
MIN_PREFIX = 4
SEVERITY_ORDER = {"критично": 0, "важно": 1, "справка": 2}


def fold(text):
    """Нижний регистр, ё=е, всё кроме букв и цифр — пробел."""
    return " ".join(WORD.findall(text.lower().replace("ё", "е")))


def stem(word):
    """Лёгкая обрезка русского окончания; латиница и числа не трогаются."""
    if not re.match(r"^[а-я]+$", word) or len(word) < 4:
        return word
    for ending in ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            return word[:-len(ending)]
    return word


def tokens(text):
    """Основы слов текста без служебных слов, порядок сохранён, повторы убраны."""
    seen, result = set(), []
    for word in fold(text).split():
        if word in STOPWORDS:
            continue
        base = stem(word)
        if base not in seen:
            seen.add(base)
            result.append(base)
    return result


class Index:
    """Индекс правил (или рецептов) манифеста; тела читаются через read_body(rule) по требованию."""

    def __init__(self, rules, read_body, text_key="симптом"):
        """text_key — поле дополнительного текста записи: «симптом» у правил, «задача» у рецептов."""
        self.read_body = read_body
        self.entries = []
        self.bodies = None
        for rule in rules:
            keys = list(rule.get("ключи", []))
            self.entries.append({
                "rule": rule,
                "id": fold(rule["id"]),
                "fields": {
                    "id": set(tokens(rule["id"])),
                    "title": set(tokens(rule["заголовок"])),
                    "keys": set(tokens(" ".join(keys))),
                    "symptom": set(tokens(rule.get(text_key, ""))),
                },
                "text": {
                    "title": fold(rule["заголовок"]),
                    "keys": fold(" ".join(keys)),
                    "symptom": fold(rule.get(text_key, "")),
                },
            })

    def _load_bodies(self):
        if self.bodies is None:
            self.bodies = {}
            for entry in self.entries:
                try:
                    text = self.read_body(entry["rule"])
                except (OSError, ValueError):
                    text = ""
                self.bodies[entry["rule"]["id"]] = (set(tokens(text)), fold(text))
        return self.bodies

    @staticmethod
    def _hit(word, stems):
        """1.0 — совпала основа, PREFIX_FACTOR — слово запроса начало основы поля, иначе 0."""
        if word in stems:
            return 1.0
        if len(word) >= MIN_PREFIX and any(item.startswith(word) for item in stems):
            return PREFIX_FACTOR
        return 0.0

    def _score(self, entry, query_tokens, phrase, with_body):
        """(сколько слов найдено, счёт). Слово считается найденным в лучшем из полей."""
        found, score = 0, 0.0
        fields = dict(entry["fields"])
        if with_body:
            fields["body"] = self._load_bodies()[entry["rule"]["id"]][0]
        for word in query_tokens:
            best = 0.0
            for name, stems in fields.items():
                hit = self._hit(word, stems)
                if hit:
                    best = max(best, hit * WEIGHTS[name])
            if best:
                found += 1
                score += best
        texts = dict(entry["text"])
        if with_body:
            texts["body"] = self._load_bodies()[entry["rule"]["id"]][1]
        if phrase and len(query_tokens) > 1:
            for name, text in texts.items():
                if phrase in text:
                    score += PHRASE_BONUS[name]
        return found, score

    def search(self, query, accept):
        """Возвращает (правила по убыванию счёта, режим). Режим: точный | по тексту | частичный."""
        raw = query.strip().lower()
        query_tokens = tokens(query)
        phrase = fold(query)
        if not query_tokens and phrase:
            query_tokens = phrase.split()
        entries = [item for item in self.entries if accept(item["rule"])]
        if not query_tokens:
            return [], "точный"

        def rank(scored):
            scored.sort(key=lambda row: (-row[0], SEVERITY_ORDER.get(row[1]["rule"].get("серьёзность"), 9),
                                         row[1]["rule"]["id"]))
            return [row[1]["rule"] for row in scored]

        for entry in entries:
            if raw == entry["rule"]["id"].lower():
                return [entry["rule"]], "точный"  # запрос — id целиком: остальное не показываем

        total = len(query_tokens)
        scored = []
        for entry in entries:
            found, score = self._score(entry, query_tokens, phrase, False)
            if ID_PREFIX.match(raw) and entry["rule"]["id"].lower().startswith(raw):
                found, score = total, score + WEIGHTS["id"]  # начало id: bsl, bsl-0, forms
            if found == total:
                scored.append((score, entry))
        if scored:
            return rank(scored), "точный"

        scored = []
        for entry in entries:
            found, score = self._score(entry, query_tokens, phrase, True)
            if found == total:
                scored.append((score, entry))
        if scored:
            return rank(scored), "по тексту"

        if total >= 3:
            need = -(-total * 3 // 5)  # не меньше 60% слов, округление вверх
            scored = []
            for entry in entries:
                found, score = self._score(entry, query_tokens, phrase, True)
                if found >= need:
                    scored.append((score, entry))
            if scored:
                return rank(scored), "частичный"
        return [], "точный"
