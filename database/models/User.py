# models/user.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from models import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    patronymic = Column(String, nullable=False)
    last_name = Column(String, nullable=False)  # исправил опечатку lsct_name
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    is_first_run = Column(Boolean, default=True)  # Для отслеживания первого запуска
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    history = relationship("History", back_populates="user", cascade="all, delete-orphan")
    collection = relationship("Collection", back_populates="user", cascade="all, delete-orphan")
    interests = relationship("UserInterest", back_populates="user", cascade="all, delete-orphan")
    searches = relationship("SearchHistory", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, name='{self.name}', email='{self.email}')>"