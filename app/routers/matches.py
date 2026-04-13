from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth_utils import get_current_user
import app.models as models
from app.schemas import MatchCard, MatchesResponse
from app.routers.matching import score_candidate

router = APIRouter()


def _latest_synapse(user_id: int, db: Session) -> models.SynapseAnswer | None:
    """Return the most recent completed SynapseAnswer for a user, or None."""
    return (
        db.query(models.SynapseAnswer)
        .filter(models.SynapseAnswer.user_id == user_id)
        .order_by(models.SynapseAnswer.completed_at.desc())
        .first()
    )


@router.get("/", response_model=MatchesResponse)
def get_matches(
    stage: int = Query(default=None, ge=1, le=4, description="Override stage (defaults to user's own stage)"),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Return ranked cofounder matches for the currently logged-in user.

    - Stage is read from the user's own profile (profile.stage) unless
      overridden via the ?stage= query param.
    - Only users who have completed at least Stage 1 (have a profile) are
      included in the candidate pool.
    - The calling user is always excluded from their own results.
    """

    # ── 1. Load the current user's data ──────────────────────────────────────
    user_profile = (
        db.query(models.Profile)
        .filter(models.Profile.user_id == current_user.id)
        .first()
    )
    if not user_profile:
        raise HTTPException(
            status_code=400,
            detail="Complete your profile (Stage 1) before viewing matches.",
        )

    effective_stage = stage if stage is not None else user_profile.stage

    user_pref = (
        db.query(models.Preference)
        .filter(models.Preference.user_id == current_user.id)
        .first()
    )

    user_synapse = _latest_synapse(current_user.id, db)

    # ── 2. Load candidate pool (everyone else with a profile) ─────────────────
    candidate_profiles: list[models.Profile] = (
        db.query(models.Profile)
        .filter(models.Profile.user_id != current_user.id)
        .all()
    )

    if not candidate_profiles:
        return MatchesResponse(
            matches=[],
            stage=effective_stage,
            total_matches=0,
            user_synapse_score=user_synapse.synapse_score if user_synapse else 0.0,
        )

    # Batch-load preferences and synapse answers for all candidates in 2 queries
    candidate_ids = [p.user_id for p in candidate_profiles]

    cand_prefs: dict[int, models.Preference] = {
        p.user_id: p
        for p in db.query(models.Preference)
        .filter(models.Preference.user_id.in_(candidate_ids))
        .all()
    }

    # One synapse row per candidate (latest per user via a subquery)
    from sqlalchemy import func as sa_func

    latest_synapse_subq = (
        db.query(
            models.SynapseAnswer.user_id,
            sa_func.max(models.SynapseAnswer.completed_at).label("max_completed"),
        )
        .filter(models.SynapseAnswer.user_id.in_(candidate_ids))
        .group_by(models.SynapseAnswer.user_id)
        .subquery()
    )

    cand_synapses: dict[int, models.SynapseAnswer] = {
        s.user_id: s
        for s in db.query(models.SynapseAnswer)
        .join(
            latest_synapse_subq,
            (models.SynapseAnswer.user_id == latest_synapse_subq.c.user_id)
            & (models.SynapseAnswer.completed_at == latest_synapse_subq.c.max_completed),
        )
        .all()
    }

    # ── 3. Score every candidate ──────────────────────────────────────────────
    scored: list[dict] = []
    for cand_profile in candidate_profiles:
        result = score_candidate(
            stage        = effective_stage,
            user_profile = user_profile,
            user_pref    = user_pref,
            user_synapse = user_synapse,
            cand_profile = cand_profile,
            cand_pref    = cand_prefs.get(cand_profile.user_id),
            cand_synapse = cand_synapses.get(cand_profile.user_id),
        )
        scored.append(result)

    # ── 4. Sort and persist top matches ──────────────────────────────────────
    scored.sort(key=lambda x: x["final_score"], reverse=True)
    top = scored[:limit]

    # Upsert into the matches table so other features (connections, history) can use it
    for rank in top:
        existing = (
            db.query(models.Match)
            .filter(
                models.Match.user_id == current_user.id,
                models.Match.matched_user_id == rank["id"],
            )
            .first()
        )
        if existing:
            existing.final_score      = rank["final_score"]
            existing.profile_score    = rank["profile_score"]
            existing.skills_score     = rank["skills_score"]
            existing.preference_score = rank["preference_score"]
            existing.synapse_score    = rank["synapse_score"]
            existing.vision_score     = rank["vision_score"]
            existing.style_score      = rank["style_score"]
        else:
            db.add(models.Match(
                user_id         = current_user.id,
                matched_user_id = rank["id"],
                final_score     = rank["final_score"],
                profile_score   = rank["profile_score"],
                skills_score    = rank["skills_score"],
                preference_score= rank["preference_score"],
                synapse_score   = rank["synapse_score"],
                vision_score    = rank["vision_score"],
                style_score     = rank["style_score"],
                status          = "pending",
            ))
    db.commit()

    # ── 5. Return response ────────────────────────────────────────────────────
    return MatchesResponse(
        matches       = [MatchCard(**m) for m in top],
        stage         = effective_stage,
        total_matches = len(top),
        user_synapse_score = user_synapse.synapse_score if user_synapse else 0.0,
    )