from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_ai_client_key
from app.schemas import AiActivityMetadataRequest, AiGenerateQuestionsRequest, AiParagraphRequest
from app.services.cloud_task_intent import CloudTaskIntent, intent_from_ocr_content_type
from app.services.llm_router import generate_with_fallback

router = APIRouter(prefix="/ai", tags=["ai"])


def _has_any_llm_key() -> bool:
    return bool(
        settings.gemini_api_key
        or settings.openai_api_key
        or settings.groq_api_key
        or settings.anthropic_api_key
        or settings.mistral_api_key
        or settings.openrouter_api_key
    )


@router.post("/activity-metadata")
async def activity_metadata(
    body: AiActivityMetadataRequest,
    db: Session = Depends(get_db),
    client_key: str | None = Depends(get_ai_client_key),
) -> dict:
    title = body.text.strip().splitlines()[0][:48] if body.text.strip() else "Activity"
    summary = body.text[:200]
    provider_id = "local-stub"

    if _has_any_llm_key():
        prompt = (
            "Generate a short activity title (max 8 words) and one-line summary for a language learning journal.\n"
            f"Text:\n{body.text[:1500]}\n"
            "Reply as: TITLE: ...\\nSUMMARY: ..."
        )
        raw, provider_id = await generate_with_fallback(
            db, prompt, max_tokens=120, client_key=client_key,
            task_intent=CloudTaskIntent.JOURNAL.value,
        )
        if raw:
            for line in raw.splitlines():
                if line.upper().startswith("TITLE:"):
                    title = line.split(":", 1)[1].strip()[:48]
                elif line.upper().startswith("SUMMARY:"):
                    summary = line.split(":", 1)[1].strip()[:200]

    return {
        "title": title,
        "summary": summary,
        "tags": ["activity"],
        "provider_used": provider_id,
    }


@router.post("/explain-paragraph")
async def explain_paragraph(
    body: AiParagraphRequest,
    db: Session = Depends(get_db),
    client_key: str | None = Depends(get_ai_client_key),
) -> dict:
    explanation = (
        f"[offline] Explanation ({body.source_lang}→{body.target_lang}): "
        f"{body.paragraph[:400]}"
    )
    provider_id = "local-stub"

    if _has_any_llm_key():
        prompt = body.paragraph.strip()
        if not prompt.lower().startswith("you are"):
            prompt = (
                f"You are a language tutor. Explain this for a learner "
                f"(source {body.source_lang}, respond in {body.target_lang}). "
                f"Be clear and detailed.\n\n{body.paragraph[:3000]}"
            )
        llm_text, provider_id = await generate_with_fallback(
            db, prompt, max_tokens=1024, client_key=client_key,
            task_intent=CloudTaskIntent.TUTOR.value,
        )
        if llm_text:
            explanation = llm_text

    return {"explanation": explanation, "provider_used": provider_id}


@router.post("/structure-ocr")
async def structure_ocr(
    body: dict,
    db: Session = Depends(get_db),
    client_key: str | None = Depends(get_ai_client_key),
) -> dict:
    """Structure noisy OCR for math, code, flowcharts — uses cloud LLM pool (not home AI)."""
    raw_text = (body.get("raw_text") or body.get("prompt") or "")[:6000]
    content_type = (body.get("content_type") or "prose").lower()
    prompt = body.get("prompt") or (
        f"Fix OCR errors and structure this {content_type} scan text:\n\n{raw_text}"
    )
    structured = raw_text
    provider_id = "local-stub"

    if _has_any_llm_key():
        llm_text, provider_id = await generate_with_fallback(
            db, prompt, max_tokens=2048, client_key=client_key,
            task_intent=intent_from_ocr_content_type(content_type).value,
        )
        if llm_text:
            structured = llm_text

    return {
        "structured_text": structured,
        "content_type": content_type,
        "provider_used": provider_id,
    }


def _parse_questions_json(raw: str | None) -> list[dict]:
    """Parse an LLM reply into a list of question dicts (strip markdown fences / prose)."""
    if not raw or not str(raw).strip():
        return []
    import json as _json
    import re as _re
    s = str(raw).strip()
    if s.startswith("```"):
        s = _re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = _re.sub(r"\s*```$", "", s)
    candidates = [s]
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(s[start:end + 1])
    start2, end2 = s.find("["), s.rfind("]")
    if start2 != -1 and end2 != -1 and end2 > start2:
        candidates.append(s[start2:end2 + 1])
    for cand in candidates:
        try:
            data = _json.loads(cand)
        except (TypeError, ValueError, _json.JSONDecodeError):
            continue
        if isinstance(data, list):
            return [q for q in data if isinstance(q, dict)]
        if isinstance(data, dict):
            questions = data.get("questions") or data.get("items") or []
            if isinstance(questions, list):
                return [q for q in questions if isinstance(q, dict)]
    return []


@router.post("/generate-questions")
async def generate_questions(
    body: AiGenerateQuestionsRequest,
    db: Session = Depends(get_db),
    client_key: str | None = Depends(get_ai_client_key),
) -> dict:
    """Generate MCQ questions from a prompt using the Cloud LLM pool (same as Android app)."""
    questions: list[dict] = []
    provider_id = "local-stub"
    if _has_any_llm_key() and body.prompt.strip():
        max_tokens = min(max(int(body.count) * 220 + 120, 400), 4096)
        raw, provider_id = await generate_with_fallback(
            db,
            body.prompt,
            max_tokens=max_tokens,
            client_key=client_key,
            task_intent=CloudTaskIntent.GENERAL.value,
        )
        parsed = _parse_questions_json(raw)
        questions = parsed[: body.count] if parsed else []
    return {
        "questions": questions,
        "provider_used": provider_id,
        "count": len(questions),
    }
