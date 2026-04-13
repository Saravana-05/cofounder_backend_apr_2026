"""
matching.py — pure scoring functions, no mock data.

Scoring weights by onboarding stage:
┌──────────────────────┬────────┬────────┬────────┐
│ Component            │ Stg 1  │ Stg 2  │ Stg 3+ │
├──────────────────────┼────────┼────────┼────────┤
│ Profile similarity   │  50 %  │  35 %  │  30 %  │
│ Skills fit           │  50 %  │  35 %  │  30 %  │
│ Preference match     │   0 %  │  30 %  │  20 %  │
│ SYNAPSE              │   0 %  │   0 %  │  20 %  │
└──────────────────────┴────────┴────────┴────────┘
"""

from __future__ import annotations
from app.models import Profile, Preference, SynapseAnswer


# ── low-level helpers ─────────────────────────────────────────────────────────

def _safe_list(value) -> list:
    """Coerce JSON/None column to a plain list."""
    if isinstance(value, list):
        return value
    return []


def _jaccard(a: list, b: list) -> float:
    """Jaccard similarity between two string lists → 0-100."""
    sa = {str(x).lower() for x in a}
    sb = {str(x).lower() for x in b}
    if not sa and not sb:
        return 50.0
    union = sa | sb
    return (len(sa & sb) / len(union)) * 100 if union else 0.0


def _keyword_overlap(user_text: str | None, candidate_text: str | None) -> float:
    """Word-level overlap between two free-text fields → 0-100."""
    if not user_text or not candidate_text:
        return 50.0
    uw = set(user_text.lower().split())
    cw = set(candidate_text.lower().split())
    union = uw | cw
    return (len(uw & cw) / len(union)) * 100 if union else 0.0


def _domain_score(user_pref: Preference | None, candidate_profile: Profile) -> float:
    """
    How well does the candidate's domain match what the user wants to build?
    Compares candidate's primary_domain against user's what_building text.
    """
    if not user_pref or not user_pref.what_building:
        return 50.0
    return _keyword_overlap(user_pref.what_building, candidate_profile.primary_domain)


def _role_score(user_pref: Preference | None, candidate_profile: Profile) -> float:
    """Does the candidate's role match what the user is seeking?"""
    if not user_pref:
        return 50.0
    seeking = _safe_list(user_pref.skills_seeking)
    if not seeking:
        return 50.0
    candidate_role = (candidate_profile.current_role or "").lower()
    for skill in seeking:
        if skill.lower() in candidate_role or candidate_role in skill.lower():
            return 100.0
    # Partial word match
    for skill in seeking:
        for word in skill.lower().split():
            if word in candidate_role:
                return 65.0
    return 10.0


def _personality_score(user_pref: Preference | None, candidate_profile: Profile) -> float:
    """
    Personality tag match.
    user_pref.cofounder_personality = what user wants in a cofounder.
    candidate_profile has no personality column directly — we infer from
    the candidate's OWN preference row (their self-described personality).
    This function receives pre-fetched candidate_personality_tags for that reason.
    """
    # Called with pre-computed tags list — see score_candidate()
    return 50.0  # placeholder; actual logic in score_candidate


def _synapse_compatibility(
    user_synapse: SynapseAnswer | None,
    candidate_synapse: SynapseAnswer | None,
) -> tuple[float, float, float]:
    """
    Returns (synapse_compat, vision_score, style_score).

    Vision / working-style → similarity (same is good).
    Risk / communication   → complementarity (opposite can be good).

    All raw scores are stored as computed traits in SynapseAnswer.traits JSON:
        {"vision": 0-100, "working_style": 0-100,
         "risk_appetite": 0-100, "communication": 0-100}
    """
    if not user_synapse or not candidate_synapse:
        return 50.0, 50.0, 50.0

    ut: dict = user_synapse.traits or {}
    ct: dict = candidate_synapse.traits or {}

    def _get(d, key):
        return float(d.get(key, 50))

    vision_sim  = max(0.0, 100.0 - abs(_get(ut, "vision")        - _get(ct, "vision")))
    style_sim   = max(0.0, 100.0 - abs(_get(ut, "working_style") - _get(ct, "working_style")))

    # Complementarity: score is higher when the two are far apart (different = complementary)
    risk_comp   = abs(_get(ut, "risk_appetite") - _get(ct, "risk_appetite"))
    comm_comp   = abs(_get(ut, "communication") - _get(ct, "communication"))

    synapse_compat = (vision_sim * 0.35 + style_sim * 0.35 + risk_comp * 0.15 + comm_comp * 0.15)
    return round(synapse_compat, 1), round(vision_sim, 1), round(style_sim, 1)


# ── main scoring function ─────────────────────────────────────────────────────

def score_candidate(
    *,
    stage: int,
    # current user data
    user_profile:  Profile,
    user_pref:     Preference | None,
    user_synapse:  SynapseAnswer | None,
    # candidate data
    cand_profile:  Profile,
    cand_pref:     Preference | None,
    cand_synapse:  SynapseAnswer | None,
) -> dict:
    """
    Score a single candidate against the logged-in user.
    Returns a dict ready to populate MatchCard.
    """

    # ── Profile similarity (domain + experience proximity) ────────────────────
    domain_sim   = _domain_score(user_pref, cand_profile)
    exp_diff     = abs((user_profile.years_of_experience or 0) - (cand_profile.years_of_experience or 0))
    exp_sim      = max(0.0, 100.0 - exp_diff * 8)   # -8 pts per year apart, floored at 0
    profile_score = (domain_sim * 0.6 + exp_sim * 0.4)

    # ── Skills fit ────────────────────────────────────────────────────────────
    user_seeking       = _safe_list(user_pref.skills_seeking if user_pref else [])
    cand_personality   = _safe_list(cand_pref.cofounder_personality if cand_pref else [])

    role_sim   = _role_score(user_pref, cand_profile)
    tag_sim    = _jaccard(user_seeking, cand_personality)
    skills_score = (role_sim * 0.7 + tag_sim * 0.3)

    # ── Preference match ──────────────────────────────────────────────────────
    if stage >= 2 and user_pref and cand_pref:
        # What user wants to build vs what candidate wants to build
        build_sim    = _keyword_overlap(user_pref.what_building, cand_pref.what_building)

        # Startup stage alignment (exact = 100, else 30)
        stage_sim    = (
            100.0 if user_pref.startup_stage == cand_pref.startup_stage
            else 30.0
        )

        # Time commitment alignment
        time_sim     = (
            100.0 if user_pref.time_commitment == cand_pref.time_commitment
            else 40.0
        )

        # Personality the user wants vs what the candidate self-describes
        user_wants_personality  = _safe_list(user_pref.cofounder_personality)
        cand_self_personality   = _safe_list(cand_pref.cofounder_personality)
        personality_sim = _jaccard(user_wants_personality, cand_self_personality)

        # Must-have filters: penalise mismatches
        user_must  = set(str(x).lower() for x in _safe_list(user_pref.must_have_filters))
        cand_must  = set(str(x).lower() for x in _safe_list(cand_pref.must_have_filters))
        must_score = (len(user_must & cand_must) / len(user_must) * 100) if user_must else 70.0

        preference_score = (
            build_sim       * 0.30 +
            stage_sim       * 0.20 +
            time_sim        * 0.15 +
            personality_sim * 0.20 +
            must_score      * 0.15
        )
    else:
        preference_score = 0.0

    # ── SYNAPSE ───────────────────────────────────────────────────────────────
    if stage >= 3:
        synapse_compat, vision_score, style_score = _synapse_compatibility(user_synapse, cand_synapse)
    else:
        synapse_compat = cand_synapse.synapse_score if cand_synapse else 0.0
        vision_score   = 50.0
        style_score    = 50.0

    # ── Weighted final score ──────────────────────────────────────────────────
    if stage == 1:
        final_score = profile_score * 0.50 + skills_score * 0.50
    elif stage == 2:
        final_score = profile_score * 0.35 + skills_score * 0.35 + preference_score * 0.30
    else:
        final_score = (
            profile_score    * 0.30 +
            skills_score     * 0.30 +
            preference_score * 0.20 +
            synapse_compat   * 0.20
        )

    # ── Avatar ────────────────────────────────────────────────────────────────
    name_parts = (cand_profile.full_name or "??").split()
    initials   = "".join(p[0].upper() for p in name_parts[:2])

    # Tags = candidate's self-described personality tags
    tags = _safe_list(cand_pref.cofounder_personality if cand_pref else [])

    return dict(
        id               = cand_profile.user_id,
        name             = cand_profile.full_name,
        role             = cand_profile.current_role or "—",
        location         = cand_profile.city or "—",
        domain           = cand_profile.primary_domain or "—",
        years_experience = cand_profile.years_of_experience or 0,
        final_score      = round(final_score, 1),
        profile_score    = round(profile_score, 1),
        skills_score     = round(skills_score, 1),
        preference_score = round(preference_score, 1),
        synapse_score    = round(synapse_compat, 1),
        vision_score     = round(vision_score, 1),
        style_score      = round(style_score, 1),
        is_blurred       = stage < 3,
        avatar_initials  = initials,
        avatar_color     = "#1565C0",   # extend later with per-user colour
        tags             = tags,
    )