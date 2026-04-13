import re
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import ProfileCreate, ProfileResponse, LinkedInImport
from app.auth_utils import get_current_user
import app.models as models

router = APIRouter()


def _validate_linkedin_url(url: str) -> str:
    url = url.strip().rstrip("/")
    pattern = re.compile(
        r"^https?://(www\.)?linkedin\.com/in/[A-Za-z0-9\-_%]+/?$"
    )
    if not pattern.match(url):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid LinkedIn URL. Expected: https://linkedin.com/in/your-username",
        )
    username = re.search(r"/in/([A-Za-z0-9\-_%]+)", url).group(1)
    return f"https://www.linkedin.com/in/{username}"


@router.post("/validate-linkedin")
async def validate_linkedin(data: LinkedInImport):
    clean_url = _validate_linkedin_url(data.linkedin_url)
    return {
        "success": True,
        "message": "LinkedIn URL is valid.",
        "linkedin_url": clean_url,
    }


# ← NEW: fetch the logged-in user's own profile using Bearer token
@router.get("/me", response_model=ProfileResponse)
async def get_my_profile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    profile = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.post("/create", response_model=ProfileResponse)
async def create_profile(
    profile_data: ProfileCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    existing = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if existing:
        for key, value in profile_data.dict(exclude_unset=True).items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    profile = models.Profile(user_id=current_user.id, **profile_data.dict())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/{user_id}", response_model=ProfileResponse)
async def get_profile(user_id: int, db: Session = Depends(get_db)):
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{user_id}", response_model=ProfileResponse)
async def update_profile(
    user_id: int,
    profile_data: ProfileCreate,
    db: Session = Depends(get_db),
):
    profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    for key, value in profile_data.dict(exclude_unset=True).items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile

