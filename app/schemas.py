from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime

# Auth Schemas
class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

# Profile Schemas
class LinkedInImport(BaseModel):
    linkedin_url: str

class ProfileCreate(BaseModel):
    full_name: str
    city: Optional[str] = None
    current_role: Optional[str] = None
    primary_domain: Optional[str] = None
    years_of_experience: Optional[int] = None
    education: Optional[str] = None
    linkedin_url: Optional[str] = None
    bio: Optional[str] = None

class ProfileResponse(BaseModel):
    id: int
    user_id: int
    full_name: str
    city: Optional[str]
    current_role: Optional[str]
    primary_domain: Optional[str]
    years_of_experience: Optional[int]
    education: Optional[str]
    linkedin_url: Optional[str]
    bio: Optional[str]
    stage: int

    class Config:
        from_attributes = True

# Preferences Schemas
class PreferenceCreate(BaseModel):
    what_building: Optional[str] = None
    startup_stage: Optional[str] = None
    time_commitment: Optional[str] = None
    skills_seeking: List[str] = []
    cofounder_personality: List[str] = []
    must_have_filters: List[str] = []

class PreferenceResponse(PreferenceCreate):
    id: int
    user_id: int

    class Config:
        from_attributes = True

# Synapse Test Schemas
class SynapseSubmit(BaseModel):
    answers: Dict[str, int]  # question_id -> score (1-7)

class SynapseResponse(BaseModel):
    synapse_score: float
    traits: Dict[str, Any]
    message: str

# Match Schemas
class MatchCard(BaseModel):
    id: int
    name: str
    role: str
    location: str
    domain: str
    years_experience: int
    final_score: float
    profile_score: float
    skills_score: float
    preference_score: float
    synapse_score: float
    vision_score: float
    style_score: float
    is_blurred: bool
    avatar_initials: str
    avatar_color: str = "#1565C0"   # added — used by frontend
    tags: List[str] = []            # added — personality tags shown as chips

class MatchesResponse(BaseModel):
    matches: List[MatchCard]
    stage: int
    total_matches: int
    user_synapse_score: float = 0.0  # current user's own SYNAPSE score for the summary banner