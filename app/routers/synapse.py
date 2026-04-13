from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import SynapseSubmit, SynapseResponse
from app.auth_utils import get_current_user
import app.models as models

router = APIRouter()

SYNAPSE_QUESTIONS = [
    {"id": "q1", "text": "I prefer to make quick decisions and iterate, rather than plan extensively before starting.", "category": "execution_style"},
    {"id": "q2", "text": "I'm comfortable with high levels of ambiguity and changing priorities.", "category": "adaptability"},
    {"id": "q3", "text": "I believe raising venture capital is essential for building a meaningful startup.", "category": "vision"},
    {"id": "q4", "text": "I'm willing to work 70+ hours per week for the first 2 years if needed.", "category": "commitment"},
    {"id": "q5", "text": "I prioritize user feedback over my own product intuition.", "category": "product_philosophy"},
    {"id": "q6", "text": "I would give up a high-paying corporate job to pursue a startup full-time.", "category": "risk_appetite"},
    {"id": "q7", "text": "I believe cofounder conflicts should be resolved through structured processes, not just conversation.", "category": "conflict_resolution"},
    {"id": "q8", "text": "I'm comfortable taking a back seat in areas outside my expertise.", "category": "ego_management"},
    {"id": "q9", "text": "I believe the market opportunity matters more than the founding team.", "category": "vision"},
    {"id": "q10", "text": "I prefer remote collaboration over working together in the same physical space.", "category": "work_style"},
    {"id": "q11", "text": "I'm willing to pivot the business model if the original idea isn't working.", "category": "adaptability"},
    {"id": "q12", "text": "I believe equity should be split based on contribution, not equally between cofounders.", "category": "values"},
    {"id": "q13", "text": "I would prioritize growth metrics over profitability in the first 3 years.", "category": "vision"},
    {"id": "q14", "text": "I'm comfortable with my cofounder having a very different communication style from mine.", "category": "interpersonal"},
    {"id": "q15", "text": "I believe a startup's culture should be deliberately designed from day one.", "category": "leadership"},
    {"id": "q16", "text": "I prefer to hire generalists early on rather than specialists.", "category": "execution_style"},
    {"id": "q17", "text": "I think a cofounder's network is more important than their technical skills.", "category": "values"},
    {"id": "q18", "text": "I'm willing to relocate to a different city if the business requires it.", "category": "commitment"},
    {"id": "q19", "text": "I believe in giving early employees significant equity to attract talent.", "category": "values"},
    {"id": "q20", "text": "I would be comfortable if my cofounder became more publicly recognized than me.", "category": "ego_management"},
]


def calculate_synapse_score(answers: dict) -> tuple[float, dict]:
    if not answers:
        return 0.0, {}
    categories = {}
    for q in SYNAPSE_QUESTIONS:
        qid = q["id"]
        cat = q["category"]
        if qid in answers:
            normalized = (answers[qid] - 1) / 6
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(normalized)
    cat_scores = {cat: sum(s) / len(s) for cat, s in categories.items()}
    overall = (sum(cat_scores.values()) / len(cat_scores)) * 100 if cat_scores else 50.0
    traits = {
        "risk_appetite": round(cat_scores.get("risk_appetite", 0.5) * 100),
        "execution_style": "iterative" if cat_scores.get("execution_style", 0.5) > 0.5 else "deliberate",
        "adaptability": round(cat_scores.get("adaptability", 0.5) * 100),
        "commitment_level": round(cat_scores.get("commitment", 0.5) * 100),
        "ego_balance": round(cat_scores.get("ego_management", 0.5) * 100),
        "vision_alignment": round(cat_scores.get("vision", 0.5) * 100),
        "leadership_style": "culture-first" if cat_scores.get("leadership", 0.5) > 0.5 else "results-first",
    }
    return round(overall, 2), traits


@router.get("/questions")
async def get_questions():
    return {"questions": SYNAPSE_QUESTIONS, "total": len(SYNAPSE_QUESTIONS)}


# ← NEW: get current user's synapse result
@router.get("/me", response_model=SynapseResponse)
async def get_my_synapse(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    result = (
        db.query(models.SynapseAnswer)
        .filter(models.SynapseAnswer.user_id == current_user.id)
        .order_by(models.SynapseAnswer.id.desc())
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail="No synapse result found")
    return {
        "synapse_score": result.synapse_score,
        "traits": result.traits,
        "message": f"SYNAPSE score: {result.synapse_score:.1f}/100",
    }


@router.post("/submit", response_model=SynapseResponse)
async def submit_synapse_test(
    data: SynapseSubmit,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),  # ← fixed
):
    score, traits = calculate_synapse_score(data.answers)

    # Upsert — replace existing result if any
    existing = (
        db.query(models.SynapseAnswer)
        .filter(models.SynapseAnswer.user_id == current_user.id)
        .first()
    )
    if existing:
        existing.answers = data.answers
        existing.synapse_score = score
        existing.traits = traits
        db.commit()
    else:
        db.add(models.SynapseAnswer(
            user_id=current_user.id,
            answers=data.answers,
            synapse_score=score,
            traits=traits,
        ))
        db.commit()

    return {
        "synapse_score": score,
        "traits": traits,
        "message": f"SYNAPSE analysis complete. Your compatibility score is {score:.1f}/100",
    }