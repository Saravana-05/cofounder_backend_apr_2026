from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import PreferenceCreate, PreferenceResponse
from app.auth_utils import get_current_user
import app.models as models

router = APIRouter()


@router.post("/save", response_model=PreferenceResponse)
async def save_preferences(
    pref_data: PreferenceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),  # ← use real user
):
    existing = db.query(models.Preference).filter(
        models.Preference.user_id == current_user.id
    ).first()

    if existing:
        for key, value in pref_data.dict(exclude_unset=True).items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    pref = models.Preference(user_id=current_user.id, **pref_data.dict())
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return pref


@router.get("/me", response_model=PreferenceResponse)
async def get_my_preferences(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    pref = db.query(models.Preference).filter(
        models.Preference.user_id == current_user.id
    ).first()
    if not pref:
        raise HTTPException(status_code=404, detail="Preferences not found")
    return pref


@router.get("/{user_id}", response_model=PreferenceResponse)
async def get_preferences(user_id: int, db: Session = Depends(get_db)):
    pref = db.query(models.Preference).filter(
        models.Preference.user_id == user_id
    ).first()
    if not pref:
        raise HTTPException(status_code=404, detail="Preferences not found")
    return pref