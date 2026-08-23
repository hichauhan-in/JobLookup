"""Prompt builders.

Kept in one file so the model's instructions can be read end to end. Two things
are load-bearing across all of them:

* **Batching.** Scoring asks about several jobs in one call, because one call
  per job through a Copilot seat is slow and burns quota for no extra accuracy.
  The reply is keyed by the id we supplied, never by position, so a model that
  drops or reorders an entry costs one score rather than corrupting the rest.
* **Stretch tolerance.** Most people are hired into roles they have not held
  before. A scorer that only rewards exact matches shows you the job you already
  have.
"""

from __future__ import annotations

import json
from typing import Any

# --- CV extraction -----------------------------------------------------------

CV_EXTRACT_SYSTEM = """You extract structured data from a CV.

Rules:
- Record only what the CV actually states. Never infer a skill that is not written down.
- Normalise skill names to their common form ("MS Azure" -> "Azure", "js" -> "JavaScript").
- years is what the CV evidences for that skill. Use 0 when unclear.
- level is one of: beginner, working, strong, expert, unknown.
- seniority is one of: intern, junior, mid, senior, lead, principal, director.
- Dates are YYYY-MM when known, otherwise an empty string.

Schema:
{
  "full_name": string,
  "headline": string,
  "location": string,
  "email": string,
  "phone": string,
  "links": [string],
  "summary": string,
  "total_years_experience": number,
  "seniority": string,
  "roles": [{"title": string, "company": string, "start": string, "end": string,
             "current": boolean, "summary": string, "achievements": [string]}],
  "skills": [{"name": string, "level": string, "years": number, "category": string}],
  "domains": [string],
  "tools": [string],
  "education": [{"degree": string, "institution": string, "year": string}],
  "certifications": [string],
  "languages": [string]
}"""


def cv_extract_user(text: str, limit: int) -> str:
    return f"CV text:\n\n{text[:limit]}"


# --- job scoring -------------------------------------------------------------

SCORE_SYSTEM = """You judge how well one candidate fits several jobs at once.

You are deliberately generous about adjacent experience. Most people are hired
into roles they have not held before. Someone who has done adjacent work and can
close the gap with a few weeks of focused learning is a real candidate, not a
mismatch.

For each job, score three dimensions from 0.0 to 1.0:
- direct_fit: the candidate has already done this exact work.
- transferable_fit: existing skills carry over even though the title or stack
  differs. Weight this heavily. Support engineering to SRE, QA to automation,
  analyst to data engineering, sysadmin to cloud engineering are all high
  transferable fits.
- growth_fit: the role is a realistic next step given the trajectory, and the
  remaining gap is learnable.

Set "blocker" to a short string ONLY for a genuine hard stop, otherwise null:
- a work authorisation or visa the candidate clearly cannot satisfy
- a security clearance the candidate does not hold
- a licence or certification that is legally mandatory (medical, legal, aviation)
- a seniority mismatch of more than two levels in either direction
Do NOT set a blocker merely because a technology is unfamiliar, or because the
years-of-experience line is higher than the candidate's.

learnable_gaps: things a motivated person could be interview-ready on in about a
week. Name the tool or the concept, never "communication skills".
hard_gaps: things that genuinely need years.
rationale: plain English addressed to the candidate, within the word limit the
user message gives. No filler, no preamble.

Return one entry for every job id you were given, using that exact id.

Schema:
{
  "scores": [
    {
      "id": string,
      "direct_fit": number,
      "transferable_fit": number,
      "growth_fit": number,
      "rationale": string,
      "matched_skills": [string],
      "learnable_gaps": [string],
      "hard_gaps": [string],
      "blocker": string | null
    }
  ]
}"""


def candidate_block(profile: dict[str, Any], skill_limit: int = 70) -> str:
    summary = {
        "headline": profile.get("headline", ""),
        "total_years_experience": profile.get("total_years_experience", 0),
        "seniority": profile.get("seniority", "unknown"),
        "recent_roles": [
            f"{role.get('title', '')} at {role.get('company', '')}"
            for role in (profile.get("roles") or [])[:5]
        ],
        "domains": (profile.get("domains") or [])[:10],
        "targeting": profile.get("target_titles") or [],
        "work_authorisation": profile.get("work_authorization", ""),
        "exclusions": profile.get("exclusions") or [],
    }
    skills = ", ".join(skill_names(profile)[:skill_limit]) or "not specified"
    return "CANDIDATE\n" + json.dumps(summary, indent=2) + f"\n\nSKILLS\n{skills}"


def score_user(
    profile: dict[str, Any],
    jobs: list[dict[str, Any]],
    description_chars: int,
    *,
    rationale_words: int = 28,
    skill_limit: int = 70,
) -> str:
    entries = [
        {
            "id": str(job["id"]),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "work_mode": job.get("work_mode", ""),
            "employment": job.get("employment", ""),
            "seniority": job.get("seniority", ""),
            "description": (job.get("description") or "")[:description_chars],
        }
        for job in jobs
    ]
    return (
        f"{candidate_block(profile, skill_limit)}\n\n"
        f"JOBS ({len(entries)})\n"
        f"{json.dumps(entries, indent=2, ensure_ascii=False)}\n\n"
        f"Keep each rationale to at most {rationale_words} words.\n"
        f"Return a score entry for each of the {len(entries)} ids above."
    )


# --- CV tailoring ------------------------------------------------------------

TAILOR_SYSTEM = """You rewrite CV content for one specific job.

Hard rules, in priority order:
1. Never invent experience. Every bullet must trace to something the candidate's
   CV already contains. Reordering, re-emphasising and rewording are allowed.
   Fabricating a project, employer, metric or responsibility is not.
2. Skills the candidate does not have belong in "upskilling" only. They must
   never appear as delivered experience.
3. Write like a competent person, not like a model:
   - Plain hyphens only. Never an em dash or an en dash.
   - Vary sentence length. Some bullets short, some longer.
   - Never use these words: leverage, delve, robust, seamless, spearheaded,
     tapestry, synergy, holistic, cutting-edge, game-changer, utilise,
     furthermore, moreover, elevate, embark, realm, landscape, testament,
     pivotal, meticulous, underscore, showcase.
   - No sentence of the form "It's not just X, it's Y".
   - Start bullets with a concrete verb and end with a result where the CV
     supplies one. Do not invent numbers.
4. Keep every claim checkable against the source CV.

Schema:
{
  "headline": string,
  "summary": string,
  "highlighted_skills": [string],
  "roles": [{"title": string, "company": string, "start": string, "end": string,
             "bullets": [string]}],
  "upskilling": [string],
  "keywords_covered": [string],
  "omitted": [string]
}"""


def tailor_user(
    profile: dict[str, Any],
    cv_text: str,
    job: dict[str, Any],
    *,
    enrichment: int,
    max_bullets: int,
) -> str:
    guidance = {
        0: "Use only wording the CV already supports. Reorder and re-emphasise; do not reframe.",
        1: "You may reframe existing experience in the job's vocabulary, provided the "
        "underlying fact is in the CV.",
        2: "You may generalise from the CV's specifics to the job's language, but every "
        "claim must still be traceable.",
    }.get(max(0, min(2, enrichment)), "")

    headline = {key: job.get(key, "") for key in ("title", "company", "location", "seniority")}
    return (
        f"TARGET JOB\n{json.dumps(headline, indent=2)}\n\n"
        f"JOB DESCRIPTION\n{(job.get('description') or '')[:6000]}\n\n"
        f"{candidate_block(profile)}\n\n"
        f"SOURCE CV\n{cv_text[:18000]}\n\n"
        f"CONSTRAINTS\nAt most {max_bullets} bullets per role. {guidance}"
    )


PREP_SYSTEM = """You write a short interview preparation sheet.

This is the counterpart to the tailored CV: everything the candidate cannot
honestly claim goes here instead, framed as what to study and what to say.

Schema:
{
  "likely_questions": [{"question": string, "why": string, "answer_outline": string}],
  "study_list": [{"topic": string, "why_it_matters": string, "how_long": string}],
  "gaps_to_address_honestly": [{"gap": string, "how_to_frame_it": string}],
  "questions_to_ask_them": [string]
}"""


def prep_user(profile: dict[str, Any], job: dict[str, Any], score: dict[str, Any]) -> str:
    gaps = {
        "learnable": score.get("learnable_gaps", []),
        "hard": score.get("hard_gaps", []),
    }
    return (
        f"TARGET JOB\n{job.get('title', '')} at {job.get('company', '')}\n\n"
        f"JOB DESCRIPTION\n{(job.get('description') or '')[:5000]}\n\n"
        f"{candidate_block(profile)}\n\n"
        f"KNOWN GAPS\n{json.dumps(gaps, indent=2)}"
    )


# --- profile ------------------------------------------------------------------

PROFILE_SUMMARY_SYSTEM = """You write the one-paragraph professional summary that sits
at the top of a career profile.

It is read by a matching system, not by a recruiter, so favour concrete nouns:
role types, technologies, domains, scale. No adjectives about character. Three
sentences at most. Plain hyphens only."""


def profile_summary_user(profile: dict[str, Any]) -> str:
    return json.dumps(
        {
            "roles": [
                {"title": role.get("title"), "company": role.get("company")}
                for role in (profile.get("roles") or [])[:8]
            ],
            "skills": skill_names(profile)[:50],
            "domains": profile.get("domains") or [],
            "total_years_experience": profile.get("total_years_experience", 0),
            "seniority": profile.get("seniority", ""),
        },
        indent=2,
    )


def skill_names(profile: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for skill in profile.get("skills") or []:
        if isinstance(skill, dict):
            name = str(skill.get("name") or "").strip()
        else:
            name = str(skill).strip()
        if name:
            names.append(name)
    return names
