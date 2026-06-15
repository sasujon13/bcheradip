from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas import AiActivityMetadataRequest, AiParagraphRequest
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
async def activity_metadata(body: AiActivityMetadataRequest, db: Session = Depends(get_db)) -> dict:
    title = body.text.strip().splitlines()[0][:48] if body.text.strip() else "Activity"
    summary = body.text[:200]
    provider_id = "local-stub"

    if _has_any_llm_key():
        prompt = (
            "Generate a short activity title (max 8 words) and one-line summary for a language learning journal.\n"
            f"Text:\n{body.text[:1500]}\n"
            "Reply as: TITLE: ...\\nSUMMARY: ..."
        )
        raw, provider_id = await generate_with_fallback(db, prompt, max_tokens=120)
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
async def explain_paragraph(body: AiParagraphRequest, db: Session = Depends(get_db)) -> dict:
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
        llm_text, provider_id = await generate_with_fallback(db, prompt, max_tokens=1024)
        if llm_text:
            explanation = llm_text

    return {"explanation": explanation, "provider_used": provider_id}


@router.post("/structure-ocr")
async def structure_ocr(body: dict, db: Session = Depends(get_db)) -> dict:
    """Structure noisy OCR for math, code, flowcharts — uses cloud LLM pool (not home AI)."""
    raw_text = (body.get("raw_text") or body.get("prompt") or "")[:6000]
    content_type = (body.get("content_type") or "prose").lower()
    prompt = body.get("prompt") or (
        f"Fix OCR errors and structure this {content_type} scan text:\n\n{raw_text}"
    )
    structured = raw_text
    provider_id = "local-stub"

    if _has_any_llm_key():
        llm_text, provider_id = await generate_with_fallback(db, prompt, max_tokens=2048)
        if llm_text:
            structured = llm_text

    return {
        "structured_text": structured,
        "content_type": content_type,
        "provider_used": provider_id,
    }
