from sqlalchemy import Column, Integer, String, DateTime, Time, ForeignKey
from sqlalchemy.orm import relationship
from models import Base

class Collection(Base):
    __tablename__ = "collection"
    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String, nullable=False)
    path = Column(String, nullable=False)
    title = Column(String, nullable=False)
    data = Column(DateTime, nullable=False)
    time_key = Column(Time, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="collection")
