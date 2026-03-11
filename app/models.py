from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    events = relationship("CalendarEvent", back_populates="user")

class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=False)
    location = Column(String, nullable=False)
    date = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="events")

class DisasterCache(Base):
    __tablename__ = "disaster_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    disaster_id = Column(String, unique=True, index=True)
    title = Column(String)
    category = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    date = Column(String)
    cached_at = Column(DateTime, default=datetime.utcnow)
