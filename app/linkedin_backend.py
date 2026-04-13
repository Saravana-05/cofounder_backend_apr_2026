"""
profiles.py  —  app/routers/profiles.py
No external API needed — validates LinkedIn URL format, user fills profile manually.
"""

import re
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import ProfileCreate, ProfileResponse, LinkedInImport
import app.models as models

router = APIRouter()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _validate_linkedin_url(url: str) -> str:
    """Validate and normalise a LinkedIn profile URL. Returns clean URL or raises 422."""
    url = url.strip().rstrip("/")
    pattern = re.compile(
        r"^https?://(www\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?$"
    )
    if not pattern.match(url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Invalid LinkedIn URL. "
                "Expected format: https://linkedin.com/in/your-username"
            ),
        )
    username = re.search(r"/in/([A-Za-z0-9\-_%]+)", url).group(1)
    return f"https://www.linkedin.com/in/{username}"


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.post("/validate-linkedin")
async def validate_linkedin(data: LinkedInImport):
    """
    Validate the LinkedIn profile URL format and return the normalised URL.
    No scraping — user fills in their own profile details after this step.
    """
    clean_url = _validate_linkedin_url(data.linkedin_url)
    return {
        "success": True,
        "message": "LinkedIn URL is valid. Please fill in your profile details below.",
        "linkedin_url": clean_url,
    }


@router.post("/create", response_model=ProfileResponse)
async def create_profile(
    profile_data: ProfileCreate,
    user_id: int = 1,
    db: Session = Depends(get_db),
):
    existing = (
        db.query(models.Profile)
        .filter(models.Profile.user_id == user_id)
        .first()
    )
    if existing:
        for key, value in profile_data.dict(exclude_unset=True).items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    profile = models.Profile(user_id=user_id, **profile_data.dict())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/{user_id}", response_model=ProfileResponse)
async def get_profile(user_id: int, db: Session = Depends(get_db)):
    profile = (
        db.query(models.Profile)
        .filter(models.Profile.user_id == user_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{user_id}", response_model=ProfileResponse)
async def update_profile(
    user_id: int,
    profile_data: ProfileCreate,
    db: Session = Depends(get_db),
):
    profile = (
        db.query(models.Profile)
        .filter(models.Profile.user_id == user_id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    for key, value in profile_data.dict(exclude_unset=True).items():
        setattr(profile, key, value)

    db.commit()
    db.refresh(profile)
    return profile
