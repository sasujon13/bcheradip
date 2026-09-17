"""
Generate exam questions (MCQ) for the Cheradip admin exam-set builder.

Uses the SAME Cloud AI service the AI Language Tutor Android app uses
(bcheradip/ailt_api -> https://cheradip.com/ailt/api/ai/generate-questions) and
falls back to Home AI (https://ai.cheradip.com/ide/chat/sync) when every Cloud AI
response errors.

Every returned question is validated (question text, answer, explanation and at
least two options must be present, and the answer must correspond to one of the
options). When exam_actions inserts these questions it stamps the author as
"Cheradip AI" (updated_by); source/subsource fields are left empty because the
questions are AI-created.
"""
import json
import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_QUESTION_FIELDS = ("question", "option_1", "option_2", "option_3", "option_4", "answer", "explanation")


def _norm(s):
    """Normalize text for option/answer comparison (lowercase, remove whitespace/punct)."""
    return re.sub(r"\s+", "", str(s or "").strip().lower())


def build_prompt(
    *,
    subject_tr,
    level_tr=None,
    class_level=None,
    chapter_no=None,
    chapter=None,
    topic_no=None,
    topic=None,
    count=5,
    sample_questions=None,
):
    """Build the LLM prompt requesting `count` unique MCQ questions on a topic."""
    lines = []
    lines.append(
        "You are an expert exam-question writer for the Bangladesh national curriculum subject "
        f"'{subject_tr}' (level: {level_tr or 'All levels'}, class: {class_level or ''})."
    )
    if chapter_no or chapter:
        lines.append(f"Chapter: {chapter_no or ''} {chapter or ''}".strip())
    lines.append(
        f"Create exactly {count} NEW, original, unique multiple-choice questions for the topic: "
        f"\"{topic or topic_no or 'general'}\"."
    )
    lines.append("Each question must have exactly 4 options (option_1..option_4) with exactly one correct answer,")
    lines.append("an `answer` field set to the EXACT text of the correct option, and a clear, correct `explanation`.")
    lines.append("Do not repeat or paraphrase the sample questions below — create brand new ones.")
    if sample_questions:
        lines.append("Sample existing questions (avoid duplicating these):")
        for sq_text in sample_questions[:8]:
            lines.append(" - " + (str(sq_text)[:300] or ""))
    lines.append("Reply with ONLY valid JSON, no markdown fences, in this exact shape:")
    lines.append(
        '{"questions":[{"question":"...","option_1":"...","option_2":"...","option_3":"...","option_4":"...",'
        '"answer":"<exact correct option text>","explanation":"...","type":"MCQ","level":"..."}]}'
    )
    return "\n".join(lines)


def extract_json(text):
    """Return the parsed JSON object inside an LLM reply (strips markdown fences / prose)."""
    if not text or not str(text).strip():
        return None
    s = str(text).strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    candidates = [s]
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(s[start:end + 1])
    start2, end2 = s.find("["), s.rfind("]")
    if start2 != -1 and end2 != -1 and end2 > start2:
        candidates.append(s[start2:end2 + 1])
    for cand in candidates:
        try:
            data = json.loads(cand)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(data, (dict, list)):
            return data
    return None


def validate_question(raw):
    """Normalize one raw question dict. Returns dict or None when invalid.

    Verifies: non-empty question, non-empty answer, non-empty explanation and at
    least two options, with the answer matching one of the options (case-insensitive
    or as an A/B/C/D index).
    """
    if not isinstance(raw, dict):
        return None
    question = str(raw.get("question") or "").strip()
    explanation = str(raw.get("explanation") or "").strip()
    if not question or not explanation:
        return None
    answer = str(raw.get("answer") or "").strip()
    if not answer:
        return None
    options = []
    for key in ("option_1", "option_2", "option_3", "option_4"):
        val = str(raw.get(key) or "").strip()
        if val:
            options.append(val)
    if len(options) < 2:
        return None
    # 1) direct text match
    matched = None
    norm_answer = _norm(answer)
    for opt in options:
        if _norm(opt) == norm_answer:
            matched = opt
            break
    # 2) index match (A/B/C/D or 1/2/3/4)
    if matched is None:
        letter_map = {"A": 0, "B": 1, "C": 2, "D": 3, "1": 0, "2": 1, "3": 2, "4": 3}
        sel = letter_map.get(answer.strip().upper().rstrip("."))
        if sel is not None and sel < len(options):
            matched = options[sel]
    if matched is None:
        return None
    while len(options) < 4:
        options.append("")
    return {
        "question": question,
        "option_1": options[0],
        "option_2": options[1],
        "option_3": options[2],
        "option_4": options[3],
        "answer": matched,
        "explanation": explanation,
        "explanation2": str(raw.get("explanation2") or "").strip(),
        "explanation3": str(raw.get("explanation3") or "").strip(),
    }


def _request_json(*, url, payload, timeout):
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _call_cloud_ai(prompt, count):
    """POST to the Cloud AI generate-questions endpoint (bcheradip/ailt_api). None on error."""
    url = (getattr(settings, "CLOUD_AI_QUESTIONS_URL", "") or "").strip()
    if not url:
        return None
    timeout = int(getattr(settings, "AI_QUESTIONS_TIMEOUT_SECONDS", 60) or 60)
    payload = {"prompt": prompt, "count": count, "language_code": "en"}
    data = _request_json(url=url, payload=payload, timeout=timeout)
    questions = data.get("questions") or []
    return questions if isinstance(questions, list) else None


def _call_home_ai(prompt, count):
    """POST to the Home AI /ide/chat/sync endpoint. None on error."""
    url = (getattr(settings, "HOME_AI_QUESTIONS_URL", "") or "").strip()
    if not url:
        return None
    timeout = int(getattr(settings, "AI_QUESTIONS_TIMEOUT_SECONDS", 60) or 60)
    max_tokens = min(max(int(count) * 220 + 120, 400), 4096)
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "model": None,
        "file_context": [],
        "stream": False,
        "max_tokens": max_tokens,
    }
    data = _request_json(url=url, payload=payload, timeout=timeout)
    content = data.get("content") or data.get("explanation") or ""
    parsed = extract_json(content)
    if not isinstance(parsed, dict):
        return None
    questions = parsed.get("questions") or parsed.get("items") or []
    return questions if isinstance(questions, list) else None


def _dedupe_questions(validated, existing_questions=None):
    """Drop duplicate questions and duplicate answers.

    A generated question is kept only if its question text AND its answer are both
    unique — within the generated batch and not already present among the topic's
    existing questions (existing_questions). First occurrence wins.
    """
    existing_q = set()
    existing_a = set()
    for ex in existing_questions or []:
        if isinstance(ex, dict):
            q = _norm(ex.get("question"))
            a = _norm(ex.get("answer"))
        elif isinstance(ex, (list, tuple)):
            q = _norm(ex[0] if len(ex) > 0 else "")
            a = _norm(ex[1] if len(ex) > 1 else "")
        else:
            q, a = "", ""
        if q:
            existing_q.add(q)
        if a:
            existing_a.add(a)
    seen_q = set()
    seen_a = set()
    out = []
    for item in validated:
        qn = _norm(item.get("question"))
        an = _norm(item.get("answer"))
        if not qn or not an:
            continue
        if qn in existing_q or qn in seen_q:
            continue
        if an in existing_a or an in seen_a:
            continue
        existing_q.add(qn)
        seen_q.add(qn)
        existing_a.add(an)
        seen_a.add(an)
        out.append(item)
    return out


def generate_questions_from_ai(
    *,
    subject_tr,
    level_tr=None,
    class_level=None,
    chapter_no=None,
    chapter=None,
    topic_no=None,
    topic=None,
    count=5,
    sample_questions=None,
    existing_questions=None,
):
    """Create validated, unique MCQ questions — Home AI first, Cloud AI fallback.

    Returns (questions, provider) where provider is one of
    'home-ai', 'cloud', 'none' (both Home AI and Cloud AI failed/absent).
    Questions are deduplicated by question text and answer (against each other and
    against existing_questions).
    """
    prompt = build_prompt(
        subject_tr=subject_tr,
        level_tr=level_tr,
        class_level=class_level,
        chapter_no=chapter_no,
        chapter=chapter,
        topic_no=topic_no,
        topic=topic,
        count=count,
        sample_questions=sample_questions,
    )

    questions = None
    provider = "none"
    # Home AI first (local PC), Cloud AI as fallback
    try:
        home = _call_home_ai(prompt, count)
        if home:
            questions = home
            provider = "home-ai"
    except requests.RequestException as exc:
        logger.warning("Home AI question generation failed: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Home AI question generation error: %s", exc)

    if not questions:
        try:
            cloud = _call_cloud_ai(prompt, count)
            if cloud:
                questions = cloud
                provider = "cloud"
        except requests.RequestException as exc:
            logger.warning("Cloud AI question generation failed: %s", exc)
        except Exception as exc:  # noqa: BLE001 - any cloud failure must fall back
            logger.warning("Cloud AI question generation error: %s", exc)

    validated = []
    for raw in questions or []:
        q = validate_question(raw)
        if q:
            validated.append(q)
        if len(validated) >= count * 3:  # headroom for dedup
            break
    validated = _dedupe_questions(validated, existing_questions)
    return validated, provider