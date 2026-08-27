"""Поиск с ИИ для раздела фильмов и сериалов.

Задача модуля — превратить запрос на естественном языке
(«комедия про роботов, чтобы посмотреть вечером с детьми») в структурированные
поисковые запросы и фильтры, которые понимают обычные провайдеры.

Работает через OpenAI-совместимый API (адрес, ключ и модель задаются в
настройках). Если ИИ выключен, ключа нет или сервис недоступен —
используется эвристический разбор без сети, поэтому поиск не ломается никогда.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import requests

from config import settings

log = logging.getLogger(__name__)

TIMEOUT = 30

SYSTEM_PROMPT = """Ты — помощник по поиску фильмов и сериалов в русскоязычном
видеосервисе. Пользователь описывает, что хочет посмотреть, своими словами.

Верни ТОЛЬКО JSON без пояснений и markdown, строго такой структуры:
{
  "queries": ["поисковый запрос 1", "поисковый запрос 2", "поисковый запрос 3"],
  "genres": ["жанр"],
  "year_from": null,
  "year_to": null,
  "min_rating": null,
  "content_type": "film" | "series" | null,
  "explanation": "одно короткое предложение по-русски"
}

Правила:
- queries: 2-4 коротких запроса на русском, как их вводят в поиск видеосервиса.
  Если пользователь назвал конкретный фильм — первым запросом дай его название.
- Не выдумывай несуществующие фильмы.
- Все поля, кроме queries и explanation, могут быть null.
"""

#: Простейший словарь жанров для работы без ИИ.
GENRE_HINTS = {
    "комеди": "комедия", "смешн": "комедия", "ржач": "комедия",
    "ужас": "ужасы", "страшн": "ужасы", "хоррор": "ужасы",
    "боевик": "боевик", "экшн": "боевик", "драк": "боевик",
    "драм": "драма", "мелодрам": "мелодрама", "романт": "мелодрама",
    "фантастик": "фантастика", "космос": "фантастика", "робот": "фантастика",
    "фэнтези": "фэнтези", "магия": "фэнтези", "волшебн": "фэнтези",
    "детектив": "детектив", "расследован": "детектив",
    "триллер": "триллер", "напряжен": "триллер",
    "мультфильм": "мультфильм", "мультик": "мультфильм", "анимац": "мультфильм",
    "аниме": "аниме",
    "документал": "документальный",
    "историч": "исторический", "война": "военный", "военн": "военный",
    "семейн": "семейный", "детск": "семейный", "с детьми": "семейный",
    "спорт": "спорт", "биограф": "биография", "приключен": "приключения",
}


@dataclass
class SearchIntent:
    """Разобранное намерение пользователя."""

    queries: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    min_rating: Optional[float] = None
    content_type: Optional[str] = None
    explanation: str = ""
    #: Разобрано ИИ или эвристикой — показываем это в интерфейсе.
    used_ai: bool = False

    @property
    def has_filters(self) -> bool:
        return any(
            (self.genres, self.year_from, self.year_to, self.min_rating, self.content_type)
        )

    def matches(self, item) -> bool:
        """Проходит ли элемент по фильтрам намерения."""
        if self.min_rating and (item.rating or 0) < self.min_rating:
            return False
        if self.year_from and item.year and item.year < self.year_from:
            return False
        if self.year_to and item.year and item.year > self.year_to:
            return False
        if self.content_type and item.content_type != self.content_type:
            # Тип часто определён эвристически, поэтому это мягкий фильтр:
            # отбрасываем, только если тип у элемента вообще известен.
            return item.content_type not in ("film", "series")
        return True


class AISearch:
    """Разбор запросов на естественном языке."""

    def __init__(self):
        self._session = requests.Session()

    # ------------------------------------------------------------------ #
    @property
    def enabled(self) -> bool:
        return bool(settings.get("ai_enabled")) and bool(
            (settings.get("ai_api_key") or "").strip()
        )

    def parse(self, query: str) -> SearchIntent:
        """Разобрать запрос. Никогда не бросает исключений."""
        query = (query or "").strip()
        if not query:
            return SearchIntent()

        if self.enabled:
            intent = self._parse_with_ai(query)
            if intent is not None:
                return intent
            log.info("ИИ недоступен, используем эвристический разбор")

        return self._parse_heuristic(query)

    # ------------------------------------------------------------------ #
    #  Через LLM
    # ------------------------------------------------------------------ #
    def _parse_with_ai(self, query: str) -> Optional[SearchIntent]:
        base_url = (settings.get("ai_base_url") or "").rstrip("/")
        api_key = (settings.get("ai_api_key") or "").strip()
        model = settings.get("ai_model") or "gpt-4o-mini"

        if not base_url or not api_key:
            return None

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
            "temperature": 0.3,
            "max_tokens": 500,
            # Не все совместимые сервисы поддерживают этот параметр,
            # поэтому ответ всё равно парсится устойчиво.
            "response_format": {"type": "json_object"},
        }

        try:
            response = self._session.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            log.warning("ИИ-поиск: сеть недоступна (%s)", exc)
            return None

        if response.status_code == 401:
            log.warning("ИИ-поиск: неверный ключ API")
            return None
        if response.status_code != 200:
            log.warning("ИИ-поиск: сервис ответил %s", response.status_code)
            return None

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as exc:
            log.warning("ИИ-поиск: неожиданный формат ответа (%s)", exc)
            return None

        data = self._extract_json(content)
        if not data:
            return None

        intent = SearchIntent(
            queries=[q for q in (data.get("queries") or []) if isinstance(q, str)][:4],
            genres=[g for g in (data.get("genres") or []) if isinstance(g, str)],
            year_from=self._as_int(data.get("year_from")),
            year_to=self._as_int(data.get("year_to")),
            min_rating=self._as_float(data.get("min_rating")),
            content_type=data.get("content_type")
            if data.get("content_type") in ("film", "series")
            else None,
            explanation=str(data.get("explanation") or ""),
            used_ai=True,
        )
        # Модель может вернуть пустой список запросов — тогда толку от неё нет.
        if not intent.queries:
            intent.queries = [query]
        return intent

    @staticmethod
    def _extract_json(content: str) -> Optional[Dict]:
        """Достать JSON, даже если модель обернула его в ```json```."""
        content = (content or "").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
        try:
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            # Иногда вокруг JSON остаётся текст — вырезаем первый объект.
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

    # ------------------------------------------------------------------ #
    #  Без ИИ
    # ------------------------------------------------------------------ #
    def _parse_heuristic(self, query: str) -> SearchIntent:
        """Разбор без сети: жанры по ключевым словам, годы и рейтинг регуляркой.

        Работает всегда — именно поэтому поиск не зависит от наличия ключа.
        """
        lower = query.lower()

        genres: List[str] = []
        for marker, genre in GENRE_HINTS.items():
            if marker in lower and genre not in genres:
                genres.append(genre)

        year_from = year_to = None
        # «2010-2015» или «с 2015 года»
        range_match = re.search(r"\b(19\d{2}|20\d{2})\s*[-–—]\s*(19\d{2}|20\d{2})\b", lower)
        if range_match:
            year_from, year_to = int(range_match.group(1)), int(range_match.group(2))
        else:
            single = re.search(r"\b(19\d{2}|20\d{2})\b", lower)
            if single:
                year_from = year_to = int(single.group(1))

        if "новинк" in lower or "свеж" in lower or "последн" in lower:
            from datetime import datetime

            year_from = year_from or datetime.now().year - 1

        min_rating = None
        rating_match = re.search(r"рейтинг\D{0,10}(\d(?:[.,]\d)?)", lower)
        if rating_match:
            min_rating = float(rating_match.group(1).replace(",", "."))
        elif any(w in lower for w in ("высок", "лучш", "топ", "хорош")):
            min_rating = 7.0

        content_type = None
        if any(w in lower for w in ("сериал", "сезон", "серия", "эпизод")):
            content_type = "series"
        elif "фильм" in lower or "кино" in lower:
            content_type = "film"

        # Основной запрос — исходная фраза, дополнительные — по жанрам.
        queries = [query]
        for genre in genres[:2]:
            candidate = f"{genre} {year_from}" if year_from else genre
            if candidate not in queries:
                queries.append(candidate)

        explanation_parts = []
        if genres:
            explanation_parts.append(f"жанры: {', '.join(genres)}")
        if year_from:
            explanation_parts.append(
                f"годы: {year_from}" + (f"–{year_to}" if year_to and year_to != year_from else "")
            )
        if min_rating:
            explanation_parts.append(f"рейтинг от {min_rating}")

        return SearchIntent(
            queries=queries[:4],
            genres=genres,
            year_from=year_from,
            year_to=year_to,
            min_rating=min_rating,
            content_type=content_type,
            explanation="; ".join(explanation_parts),
            used_ai=False,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _as_int(value) -> Optional[int]:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _as_float(value) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None


#: Общий экземпляр.
ai_search = AISearch()
