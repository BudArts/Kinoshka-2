# models/history.py
from sqlalchemy import Column, Integer, String, DateTime, Time, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from models import Base
from datetime import datetime

class History(Base):
    __tablename__ = "history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Основная информация
    type = Column(String, nullable=False)  # video, music, film, series
    platform = Column(String, nullable=True)  # youtube, rutube, spotify, etc.
    video_id = Column(String, nullable=True)  # ID из YouTube/RuTube
    link = Column(String, nullable=False)
    title = Column(String, nullable=False)
    
    # Данные просмотра
    watch_duration = Column(Integer, nullable=True)  # Сколько посмотрели (секунды)
    total_duration = Column(Integer, nullable=True)  # Общая длительность (секунды)
    completed = Column(Boolean, default=False)  # Досмотрено ли до конца
    
    # Метаданные для рекомендаций
    categories = Column(String, nullable=True)  # JSON array
    tags = Column(String, nullable=True)  # JSON array
    
    # Временные метки
    date = Column(DateTime, nullable=False, default=datetime.now)
    time_key = Column(Time, nullable=False)
    
    user = relationship("User", back_populates="history")
    
    def __repr__(self):
        return f"<History(id={self.id}, type='{self.type}', title='{self.title}')>"