from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    profile = relationship("Profile", back_populates="user", uselist=False)
    preferences = relationship("Preference", back_populates="user", uselist=False)
    synapse_answers = relationship("SynapseAnswer", back_populates="user")

class Profile(Base):
    __tablename__ = "profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    full_name = Column(String, nullable=False)
    city = Column(String)
    current_role = Column(String)
    primary_domain = Column(String)
    years_of_experience = Column(Integer)
    education = Column(String)
    linkedin_url = Column(String)
    bio = Column(Text)
    avatar_url = Column(String)
    stage = Column(Integer, default=1)  # onboarding stage
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="profile")

class Preference(Base):
    __tablename__ = "preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    what_building = Column(Text)
    startup_stage = Column(String)
    time_commitment = Column(String)
    skills_seeking = Column(JSON, default=[])
    cofounder_personality = Column(JSON, default=[])
    must_have_filters = Column(JSON, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", back_populates="preferences")

class SynapseAnswer(Base):
    __tablename__ = "synapse_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    answers = Column(JSON)  # {question_id: score (1-7)}
    synapse_score = Column(Float)
    traits = Column(JSON)   # computed personality traits
    completed_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="synapse_answers")

class Match(Base):
    __tablename__ = "matches"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    matched_user_id = Column(Integer, ForeignKey("users.id"))
    profile_score = Column(Float, default=0.0)
    skills_score = Column(Float, default=0.0)
    preference_score = Column(Float, default=0.0)
    synapse_score = Column(Float, default=0.0)
    final_score = Column(Float, default=0.0)
    vision_score = Column(Float, default=0.0)
    style_score = Column(Float, default=0.0)
    status = Column(String, default="pending")  # pending, connected, rejected
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Connection(Base):
    """
    Tracks the state of a connect request between two users.
    sender_id  → the user who clicked "Connect"
    receiver_id → the user who received the request
    status: pending | accepted | rejected
    """
    __tablename__ = "connections"
 
    id          = Column(Integer, primary_key=True, index=True)
    sender_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    receiver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status      = Column(String, default="pending")   # pending | accepted | rejected
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
 
    sender   = relationship("User", foreign_keys=[sender_id])
    receiver = relationship("User", foreign_keys=[receiver_id])
    messages = relationship("ChatMessage", back_populates="connection", cascade="all, delete-orphan")
 
 
class ChatMessage(Base):
    """One chat message inside an accepted connection thread."""
    __tablename__ = "chat_messages"
 
    id            = Column(Integer, primary_key=True, index=True)
    connection_id = Column(Integer, ForeignKey("connections.id"), nullable=False)
    sender_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    content       = Column(Text, nullable=False)
    is_read       = Column(Boolean, default=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
 
    connection = relationship("Connection", back_populates="messages")
    sender     = relationship("User", foreign_keys=[sender_id])