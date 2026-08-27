from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from database.models.User import User
from database.models.User_interests import UserInterest, SearchHistory, VideoMetadata
from database.models.History import History
from datetime import datetime, timedelta
import json
from typing import List, Dict, Optional

class RecommendationEngine:
    DEFAULT_CATEGORIES = [
        'Музыка', 'Развлечения', 'Игры', 'Технологии',
        'Образование', 'Новости', 'Спорт', 'Кино и сериалы',
        'Готовка', 'Путешествия', 'Наука', 'Блоги'
    ]
    
    def __init__(self, db: Session):
        self.db = db
    
    def setup_initial_interests(self, user_id: int, selected_categories: Optional[List[str]] = None):
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User with id {user_id} not found")
        if selected_categories is None:
            selected_categories = self.DEFAULT_CATEGORIES
            weight = 0.5
        else:
            weight = 1.0

        for category in selected_categories:
            interest = UserInterest(
                user_id=user_id,
                category=category,
                weight=weight
            )
            self.db.add(interest)

        user.is_first_run = False
        self.db.commit()
    
    def track_video_watch(
        self, 
        user_id: int,
        video_data: Dict,
        watch_duration: int,
        total_duration: int
    ):
        """
        Отслеживание просмотра видео
        
        video_data = {
            'video_id': 'abc123',
            'title': 'Название видео',
            'platform': 'youtube',
            'type': 'video',
            'link': 'https://...',
            'categories': ['Технологии', 'Образование'],
            'tags': ['python', 'программирование']
        }
        """
        completion_rate = watch_duration / total_duration if total_duration > 0 else 0
        completed = completion_rate > 0.7

        history_entry = History(
            user_id=user_id,
            type=video_data.get('type', 'video'),
            platform=video_data.get('platform'),
            video_id=video_data.get('video_id'),
            link=video_data['link'],
            title=video_data['title'],
            watch_duration=watch_duration,
            total_duration=total_duration,
            completed=completed,
            categories=json.dumps(video_data.get('categories', [])),
            tags=json.dumps(video_data.get('tags', [])),
            date=datetime.now(),
            time_key=datetime.now().time()
        )
        
        self.db.add(history_entry)

        self._update_video_metadata(video_data, total_duration)

        self._update_interests_from_watch(
            user_id, 
            video_data.get('categories', []),
            completed,
            completion_rate
        )
        
        self.db.commit()
    
    def track_search(self, user_id: int, query: str, platform: str = None, clicked_video_id: str = None):
        """Отслеживание поискового запроса"""
        search = SearchHistory(
            user_id=user_id,
            query=query,
            platform=platform,
            clicked_video_id=clicked_video_id
        )
        
        self.db.add(search)
        
        # Обновление интересов на основе поиска
        self._update_interests_from_search(user_id, query)
        
        self.db.commit()
    
    def _update_video_metadata(self, video_data: Dict, duration: int):
        """Сохранение метаданных видео"""
        video_id = video_data.get('video_id')
        if not video_id:
            return
        
        metadata = self.db.query(VideoMetadata).filter(
            VideoMetadata.video_id == video_id
        ).first()
        
        if metadata:
            # Обновление существующих метаданных
            metadata.title = video_data['title']
            metadata.categories = json.dumps(video_data.get('categories', []))
            metadata.tags = json.dumps(video_data.get('tags', []))
            metadata.duration = duration
            metadata.last_updated = datetime.now()
        else:
            # Создание новых метаданных
            metadata = VideoMetadata(
                video_id=video_id,
                platform=video_data.get('platform'),
                title=video_data['title'],
                categories=json.dumps(video_data.get('categories', [])),
                tags=json.dumps(video_data.get('tags', [])),
                duration=duration
            )
            self.db.add(metadata)
    
    def _update_interests_from_watch(
        self, 
        user_id: int, 
        categories: List[str], 
        completed: bool,
        completion_rate: float
    ):
        """Обновление интересов на основе просмотра"""
        # Расчет дельты веса
        if completed:
            weight_delta = 0.3
        elif completion_rate > 0.5:
            weight_delta = 0.2
        elif completion_rate > 0.3:
            weight_delta = 0.1
        else:
            weight_delta = 0.05
        
        for category in categories:
            interest = self.db.query(UserInterest).filter(
                UserInterest.user_id == user_id,
                UserInterest.category == category
            ).first()
            
            if interest:
                # Обновление существующего интереса (максимум 5.0)
                interest.weight = min(interest.weight + weight_delta, 5.0)
                interest.last_updated = datetime.now()
            else:
                # Создание нового интереса
                interest = UserInterest(
                    user_id=user_id,
                    category=category,
                    weight=weight_delta
                )
                self.db.add(interest)
    
    def _update_interests_from_search(self, user_id: int, query: str):
        """Обновление интересов на основе поиска"""
        query_lower = query.lower()
        keywords = query_lower.split()
        
        # Получение всех интересов пользователя
        interests = self.db.query(UserInterest).filter(
            UserInterest.user_id == user_id
        ).all()
        
        for interest in interests:
            # Проверка совпадения с категорией
            if any(keyword in interest.category.lower() for keyword in keywords):
                interest.weight = min(interest.weight + 0.15, 5.0)
                interest.last_updated = datetime.now()
    
    def get_user_interests(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Получение топ интересов пользователя"""
        interests = self.db.query(UserInterest).filter(
            UserInterest.user_id == user_id
        ).order_by(desc(UserInterest.weight)).limit(limit).all()
        
        return [
            {
                'category': interest.category,
                'weight': interest.weight,
                'last_updated': interest.last_updated
            }
            for interest in interests
        ]
    
    def get_recommendations(self, user_id: int, limit: int = 20) -> List[Dict]:
        """Получение рекомендаций для пользователя"""
        # Получение топ-5 интересов
        top_interests = self.db.query(UserInterest).filter(
            UserInterest.user_id == user_id
        ).order_by(desc(UserInterest.weight)).limit(5).all()
        
        if not top_interests:
            # Если интересов нет, вернуть пустой список или популярное
            return []
        
        # Здесь вы можете интегрировать запросы к YouTube/RuTube API
        recommendations = []
        
        for interest in top_interests:
            # Примерная структура - замените на реальные API запросы
            videos = self._fetch_videos_by_category(
                interest.category, 
                limit=5
            )
            
            for video in videos:
                video['relevance_score'] = interest.weight
                recommendations.append(video)
        
        # Удаление просмотренных видео
        recommendations = self._filter_watched_videos(user_id, recommendations)
        
        # Сортировка и ограничение
        recommendations.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
        
        return recommendations[:limit]
    
    def _filter_watched_videos(self, user_id: int, videos: List[Dict]) -> List[Dict]:
        """Фильтрация уже просмотренных видео"""
        # Получение ID просмотренных видео за последние 30 дней
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        watched_ids = self.db.query(History.video_id).filter(
            History.user_id == user_id,
            History.video_id.isnot(None),
            History.date >= thirty_days_ago
        ).all()
        
        watched_ids_set = {vid[0] for vid in watched_ids}
        
        # Фильтрация
        return [
            video for video in videos 
            if video.get('video_id') not in watched_ids_set
        ]
    
    def _fetch_videos_by_category(self, category: str, limit: int = 5) -> List[Dict]:
        """
        Заглушка для получения видео по категории
        Здесь должна быть интеграция с YouTube/RuTube API
        """
        # TODO: Реализовать запросы к API
        return []
    
    def personalize_search_results(
        self, 
        user_id: int, 
        raw_results: List[Dict]
    ) -> List[Dict]:
        """Персонализация результатов поиска"""
        # Получение интересов пользователя
        interests = self.db.query(UserInterest).filter(
            UserInterest.user_id == user_id
        ).all()
        
        interests_dict = {i.category: i.weight for i in interests}
        
        # Добавление персонализированного скора
        for video in raw_results:
            base_score = video.get('relevance_score', 1.0)
            interest_boost = 0
            
            # Проверка категорий видео
            video_categories = video.get('categories', [])
            if isinstance(video_categories, str):
                video_categories = json.loads(video_categories)
            
            for category in video_categories:
                if category in interests_dict:
                    interest_boost += interests_dict[category] * 0.1
            
            video['personalized_score'] = base_score + interest_boost
        
        # Сортировка по персонализированному скору
        raw_results.sort(key=lambda x: x.get('personalized_score', 0), reverse=True)
        
        return raw_results
    
    def decay_old_interests(self, user_id: int, days: int = 30):
        """Уменьшение веса старых интересов"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        old_interests = self.db.query(UserInterest).filter(
            UserInterest.user_id == user_id,
            UserInterest.last_updated < cutoff_date
        ).all()
        
        for interest in old_interests:
            interest.weight = max(interest.weight * 0.9, 0.1)  # Минимум 0.1
        
        self.db.commit()
    
    def get_analytics(self, user_id: int) -> Dict:
        """Получение аналитики для пользователя"""
        # Топ категории
        top_categories = self.get_user_interests(user_id, limit=10)
        
        # Статистика просмотров
        stats = self.db.query(
            func.count(History.id).label('total_videos'),
            func.sum(History.watch_duration).label('total_time'),
            func.avg(
                func.cast(History.watch_duration, Float) / 
                func.nullif(History.total_duration, 0)
            ).label('avg_completion')
        ).filter(
            History.user_id == user_id
        ).first()
        
        # Активность по платформам
        platform_stats = self.db.query(
            History.platform,
            func.count(History.id).label('count')
        ).filter(
            History.user_id == user_id
        ).group_by(History.platform).all()
        
        return {
            'top_categories': top_categories,
            'total_videos_watched': stats.total_videos or 0,
            'total_watch_time_seconds': stats.total_time or 0,
            'avg_completion_rate': float(stats.avg_completion or 0),
            'platform_distribution': [
                {'platform': p, 'count': c} for p, c in platform_stats
            ]
        }