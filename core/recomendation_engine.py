"""Движок интересов и рекомендаций.

Сигналы, из которых строится профиль вкусов пользователя:
  * просмотры (вес зависит от доли досмотренного);
  * поисковые запросы;
  * затухание старых интересов со временем.

Движок не ходит в сеть сам: он отдаёт список поисковых запросов
(build_query_seeds), по которым провайдер собирает ленту, и ранжирует
полученные результаты (personalize).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import Float, desc, func
from sqlalchemy.orm import Session

from core.media import MediaItem
from database.models import History, SearchHistory, User, UserInterest, VideoMetadata

log = logging.getLogger(__name__)

#: Максимальный и минимальный вес интереса.
MAX_WEIGHT = 5.0
MIN_WEIGHT = 0.1

#: Слова, которые не несут смысла для интересов.
STOPWORDS = {
    "и", "в", "во", "не", "что", "он", "на", "я", "с", "со", "как", "а", "то",
    "все", "она", "так", "его", "но", "да", "ты", "к", "у", "же", "вы", "за",
    "бы", "по", "только", "ее", "мне", "было", "вот", "от", "меня", "еще",
    "нет", "о", "из", "ему", "теперь", "когда", "даже", "ну", "вдруг", "ли",
    "если", "уже", "или", "ни", "быть", "был", "него", "до", "вас", "нибудь",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "it",
    "смотреть", "онлайн", "бесплатно", "video", "видео", "скачать",
}


class RecommendationEngine:
    """Работа с интересами, историей и персонализацией выдачи."""

    DEFAULT_CATEGORIES = [
        "Музыка", "Развлечения", "Игры", "Технологии",
        "Образование", "Новости", "Спорт", "Кино и сериалы",
        "Готовка", "Путешествия", "Наука", "Блоги",
    ]

    def __init__(self, db: Session):
        self.db = db

    # ================================================================== #
    #  Первичная настройка
    # ================================================================== #
    def setup_initial_interests(
        self, user_id: int, selected_categories: Optional[Sequence[str]] = None
    ) -> None:
        """Задать стартовые интересы при создании профиля.

        Если пользователь выбрал категории сам — вес 1.0; если пропустил шаг,
        раздаём все категории с малым весом 0.5, чтобы лента не была пустой.
        """
        user = self.db.get(User, user_id)
        if not user:
            raise ValueError(f"Пользователь с id={user_id} не найден")

        if not selected_categories:
            selected_categories = self.DEFAULT_CATEGORIES
            weight = 0.5
        else:
            weight = 1.0

        for category in selected_categories:
            self._bump(user_id, category, weight, absolute=True)

        user.is_first_run = False
        self.db.commit()

    # ================================================================== #
    #  Сбор сигналов
    # ================================================================== #
    def track_watch(
        self,
        user_id: int,
        item: MediaItem,
        watch_duration: int,
        total_duration: Optional[int] = None,
    ) -> None:
        """Записать просмотр и обновить интересы.

        Принимает MediaItem — единый формат для всех источников.
        """
        total_duration = total_duration or item.duration or 0
        completion_rate = (
            min(watch_duration / total_duration, 1.0) if total_duration > 0 else 0.0
        )
        completed = completion_rate > 0.7

        now = datetime.now()
        entry = History(
            user_id=user_id,
            type=item.content_type,
            platform=item.platform,
            video_id=item.id,
            link=item.url,
            title=item.title,
            thumbnail=item.thumbnail,
            author=item.author,
            watch_duration=int(watch_duration),
            total_duration=int(total_duration),
            position=int(watch_duration),
            completed=completed,
            categories=json.dumps(item.categories, ensure_ascii=False),
            tags=json.dumps(item.tags, ensure_ascii=False),
            date=now,
            time_key=now.time(),
        )
        self.db.add(entry)

        self.cache_metadata(item)
        self._update_interests_from_watch(
            user_id, self._signal_terms(item), completed, completion_rate
        )
        self.db.commit()

    def track_search(
        self,
        user_id: int,
        query: str,
        platform: Optional[str] = None,
        content_type: Optional[str] = None,
        results_count: Optional[int] = None,
        clicked_video_id: Optional[str] = None,
    ) -> None:
        """Записать поисковый запрос и подкрутить интересы."""
        self.db.add(
            SearchHistory(
                user_id=user_id,
                query=query,
                platform=platform,
                content_type=content_type,
                results_count=results_count,
                clicked_video_id=clicked_video_id,
                timestamp=datetime.now(),
            )
        )
        self._update_interests_from_search(user_id, query)
        self.db.commit()

    def cache_metadata(self, item: MediaItem) -> None:
        """Сохранить/обновить метаданные единицы контента."""
        if not item.id:
            return
        metadata = (
            self.db.query(VideoMetadata)
            .filter(
                VideoMetadata.video_id == item.id,
                VideoMetadata.platform == item.platform,
            )
            .first()
        )
        if metadata is None:
            metadata = VideoMetadata(video_id=item.id, platform=item.platform)
            self.db.add(metadata)

        metadata.title = item.title
        metadata.author = item.author
        metadata.thumbnail = item.thumbnail
        metadata.url = item.url
        metadata.description = (item.description or "")[:2000] or None
        metadata.categories = json.dumps(item.categories, ensure_ascii=False)
        metadata.tags = json.dumps(item.tags, ensure_ascii=False)
        metadata.duration = item.duration
        metadata.view_count = item.view_count
        metadata.rating = item.rating
        metadata.year = item.year
        metadata.content_type = item.content_type
        metadata.last_updated = datetime.now()

    # ================================================================== #
    #  Обновление весов
    # ================================================================== #
    def _update_interests_from_watch(
        self,
        user_id: int,
        terms: Iterable[str],
        completed: bool,
        completion_rate: float,
    ) -> None:
        """Досмотрел до конца — сильный сигнал, закрыл сразу — почти никакой."""
        if completed:
            delta = 0.30
        elif completion_rate > 0.5:
            delta = 0.20
        elif completion_rate > 0.3:
            delta = 0.10
        else:
            delta = 0.05

        for term in terms:
            self._bump(user_id, term, delta)

    def _update_interests_from_search(self, user_id: int, query: str) -> None:
        """Поиск — явное намерение, поэтому вес растёт заметно."""
        keywords = self._keywords(query)
        if not keywords:
            return

        # Поисковая фраза целиком — самый точный сигнал.
        phrase = " ".join(keywords[:3])
        self._bump(user_id, phrase, 0.25)

        # Совпадения с уже известными категориями усиливаем дополнительно.
        interests = (
            self.db.query(UserInterest).filter(UserInterest.user_id == user_id).all()
        )
        for interest in interests:
            category_lower = interest.category.lower()
            if any(keyword in category_lower for keyword in keywords):
                interest.weight = min(interest.weight + 0.15, MAX_WEIGHT)
                interest.hits = (interest.hits or 0) + 1
                interest.last_updated = datetime.now()

    def _bump(
        self, user_id: int, category: str, delta: float, absolute: bool = False
    ) -> None:
        """Увеличить (или задать) вес интереса, не выходя за границы."""
        category = (category or "").strip()
        if not category or len(category) < 2:
            return

        interest = (
            self.db.query(UserInterest)
            .filter(
                UserInterest.user_id == user_id,
                UserInterest.category == category,
            )
            .first()
        )
        if interest is None:
            self.db.add(
                UserInterest(
                    user_id=user_id,
                    category=category,
                    weight=min(delta, MAX_WEIGHT),
                    hits=1,
                    last_updated=datetime.now(),
                )
            )
            return

        interest.weight = (
            min(delta, MAX_WEIGHT)
            if absolute
            else min(interest.weight + delta, MAX_WEIGHT)
        )
        interest.hits = (interest.hits or 0) + 1
        interest.last_updated = datetime.now()

    def decay_old_interests(self, user_id: int, days: int = 30) -> None:
        """Плавно гасить интересы, которые давно не подтверждались."""
        cutoff = datetime.now() - timedelta(days=days)
        stale = (
            self.db.query(UserInterest)
            .filter(
                UserInterest.user_id == user_id,
                UserInterest.last_updated < cutoff,
            )
            .all()
        )
        for interest in stale:
            interest.weight = max(interest.weight * 0.9, MIN_WEIGHT)
        self.db.commit()

    # ================================================================== #
    #  Чтение интересов
    # ================================================================== #
    def get_user_interests(self, user_id: int, limit: int = 10) -> List[Dict]:
        interests = (
            self.db.query(UserInterest)
            .filter(UserInterest.user_id == user_id)
            .order_by(desc(UserInterest.weight))
            .limit(limit)
            .all()
        )
        return [
            {
                "category": i.category,
                "weight": round(i.weight, 2),
                "hits": i.hits,
                "last_updated": i.last_updated,
            }
            for i in interests
        ]

    def build_query_seeds(
        self, user_id: int, count: int = 6, content_type: Optional[str] = None
    ) -> List[str]:
        """Список поисковых запросов для сбора ленты рекомендаций.

        Смешиваем топовые интересы и свежие поисковые запросы: первое даёт
        стабильность ленты, второе — реакцию на сиюминутные вкусы.
        """
        seeds: List[str] = []

        top_interests = (
            self.db.query(UserInterest)
            .filter(UserInterest.user_id == user_id)
            .order_by(desc(UserInterest.weight))
            .limit(count)
            .all()
        )
        seeds.extend(i.category for i in top_interests)

        recent_query = (
            self.db.query(SearchHistory)
            .filter(SearchHistory.user_id == user_id)
        )
        if content_type:
            recent_query = recent_query.filter(
                SearchHistory.content_type == content_type
            )
        recent = (
            recent_query.order_by(desc(SearchHistory.timestamp))
            .limit(max(2, count // 3))
            .all()
        )
        seeds.extend(s.query for s in recent)

        # Убираем дубли, сохраняя порядок.
        unique: List[str] = []
        seen = set()
        for seed in seeds:
            key = seed.lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(seed)
        return unique[:count]

    # ================================================================== #
    #  Ранжирование выдачи
    # ================================================================== #
    def personalize(
        self, user_id: int, items: List[MediaItem], drop_watched: bool = True
    ) -> List[MediaItem]:
        """Отсортировать элементы под интересы пользователя."""
        if not items:
            return []

        weights = {
            i.category.lower(): i.weight
            for i in self.db.query(UserInterest)
            .filter(UserInterest.user_id == user_id)
            .all()
        }

        if drop_watched:
            items = self.filter_watched(user_id, items)

        def score(item: MediaItem) -> float:
            value = 0.0
            for term in self._signal_terms(item):
                term_lower = term.lower()
                if term_lower in weights:
                    value += weights[term_lower]
                else:
                    # Частичное совпадение тоже кое-что значит.
                    for category, weight in weights.items():
                        if term_lower in category or category in term_lower:
                            value += weight * 0.4
                            break
            # Лёгкий бонус за популярность, чтобы при равных интересах
            # наверх шло то, что смотрят другие.
            if item.view_count:
                value += min(item.view_count / 10_000_000, 1.0) * 0.5
            if item.rating:
                value += item.rating / 10.0
            return value

        scored = [(score(item), index, item) for index, item in enumerate(items)]
        # index в ключе сортировки сохраняет исходный порядок при равных очках.
        scored.sort(key=lambda triple: (-triple[0], triple[1]))
        return [item for _, _, item in scored]

    def filter_watched(self, user_id: int, items: List[MediaItem]) -> List[MediaItem]:
        """Убрать из ленты то, что уже досмотрено."""
        watched = {
            row[0]
            for row in self.db.query(History.video_id)
            .filter(
                History.user_id == user_id,
                History.completed.is_(True),
                History.video_id.isnot(None),
            )
            .all()
        }
        return [item for item in items if item.id not in watched] or items

    # ================================================================== #
    #  История
    # ================================================================== #
    def get_history(
        self,
        user_id: int,
        content_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[History]:
        query = self.db.query(History).filter(History.user_id == user_id)
        if content_type:
            if content_type == "film":
                query = query.filter(History.type.in_(("film", "series")))
            else:
                query = query.filter(History.type == content_type)
        return query.order_by(desc(History.date)).limit(limit).all()

    def get_continue_watching(self, user_id: int, limit: int = 12) -> List[History]:
        """Начатое, но не досмотренное — блок «Продолжить просмотр»."""
        return (
            self.db.query(History)
            .filter(
                History.user_id == user_id,
                History.completed.is_(False),
                History.position > 30,
            )
            .order_by(desc(History.date))
            .limit(limit)
            .all()
        )

    def clear_history(self, user_id: int, content_type: Optional[str] = None) -> None:
        query = self.db.query(History).filter(History.user_id == user_id)
        if content_type:
            query = query.filter(History.type == content_type)
        query.delete(synchronize_session=False)
        self.db.commit()

    def recent_searches(self, user_id: int, limit: int = 8) -> List[str]:
        """Недавние уникальные запросы — для подсказок в строке поиска."""
        rows = (
            self.db.query(SearchHistory.query)
            .filter(SearchHistory.user_id == user_id)
            .order_by(desc(SearchHistory.timestamp))
            .limit(limit * 3)
            .all()
        )
        unique: List[str] = []
        seen = set()
        for (query_text,) in rows:
            key = query_text.lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(query_text)
            if len(unique) >= limit:
                break
        return unique

    # ================================================================== #
    #  Аналитика
    # ================================================================== #
    def get_analytics(self, user_id: int) -> Dict:
        """Сводка по профилю для экрана настроек."""
        stats = (
            self.db.query(
                func.count(History.id).label("total_videos"),
                func.sum(History.watch_duration).label("total_time"),
                func.avg(
                    func.cast(History.watch_duration, Float)
                    / func.nullif(History.total_duration, 0)
                ).label("avg_completion"),
            )
            .filter(History.user_id == user_id)
            .first()
        )

        platform_stats = (
            self.db.query(History.platform, func.count(History.id))
            .filter(History.user_id == user_id)
            .group_by(History.platform)
            .all()
        )
        type_stats = (
            self.db.query(History.type, func.count(History.id))
            .filter(History.user_id == user_id)
            .group_by(History.type)
            .all()
        )

        return {
            "top_categories": self.get_user_interests(user_id, limit=10),
            "total_videos_watched": stats.total_videos or 0,
            "total_watch_time_seconds": int(stats.total_time or 0),
            "avg_completion_rate": float(stats.avg_completion or 0),
            "platform_distribution": [
                {"platform": p or "неизвестно", "count": c} for p, c in platform_stats
            ],
            "type_distribution": [
                {"type": t or "видео", "count": c} for t, c in type_stats
            ],
            "searches_count": self.db.query(func.count(SearchHistory.id))
            .filter(SearchHistory.user_id == user_id)
            .scalar()
            or 0,
        }

    # ================================================================== #
    #  Вспомогательное
    # ================================================================== #
    @staticmethod
    def _keywords(text: str) -> List[str]:
        """Значимые слова запроса без стоп-слов и мусора."""
        words = re.findall(r"[\w-]{3,}", (text or "").lower(), flags=re.UNICODE)
        return [w for w in words if w not in STOPWORDS][:6]

    @staticmethod
    def _signal_terms(item: MediaItem) -> List[str]:
        """Термины единицы контента, влияющие на интересы."""
        terms: List[str] = []
        terms.extend(item.categories)
        terms.extend(item.tags[:5])
        if item.author:
            terms.append(item.author)
        # Убираем дубли, сохраняя порядок.
        seen = set()
        unique = []
        for term in terms:
            key = (term or "").lower().strip()
            if key and key not in seen:
                seen.add(key)
                unique.append(term)
        return unique
