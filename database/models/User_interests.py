# models/user_interests.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from models import Base
from datetime import datetime

class UserInterest(Base):
    """Интересы пользователя"""
    __tablename__ = "user_interests"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category = Column(String, nullable=False)
    weight = Column(Float, default=1.0)  # Вес интереса (0.0 - 5.0)
    last_updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    user = relationship("User", back_populates="interests")
    
    def __repr__(self):
        return f"<UserInterest(user_id={self.user_id}, category='{self.category}', weight={self.weight})>"


class SearchHistory(Base):
    """История поисковых запросов"""
    __tablename__ = "search_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    query = Column(String, nullable=False)
    platform = Column(String, nullable=True)  # youtube, rutube, music, etc.
    clicked_video_id = Column(String, nullable=True)  # ID видео, на которое кликнули
    timestamp = Column(DateTime, default=datetime.now)
    
    user = relationship("User", back_populates="searches")
    
    def __repr__(self):
        return f"<SearchHistory(user_id={self.user_id}, query='{self.query}')>"


class VideoMetadata(Base):
    """Метаданные видео для улучшения рекомендаций"""
    __tablename__ = "video_metadata"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, unique=True, nullable=False)  # ID из YouTube/RuTube
    platform = Column(String, nullable=False)  # youtube, rutube
    title = Column(String, nullable=False)
    categories = Column(String, nullable=True)  # JSON array
    tags = Column(String, nullable=True)  # JSON array
    duration = Column(Integer, nullable=True)  # в секундах
    last_updated = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<VideoMetadata(video_id='{self.video_id}', platform='{self.platform}')>"