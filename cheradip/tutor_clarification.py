"""A bounded intent check returns the extension's existing clarification UI contract."""
import json
import requests
from django.conf import settings
from .tutor_routing import FAST
from .tutor_stream import unusable
from .tutor_inference import complete


def clarification(payload, scope, base_url):
    if scope.get('selected_topic'):
        return None
    policy = (
        'You are an intent classifier for an educational tutor. Return ONLY a JSON object. '
        'If the latest request is clear enough to answer, return {"clarify":false}. '
        'A clear factual question, greeting, or explicit request for a general overview needs no clarification. '
        'An unidentified short title such as My Sister can mean a family member or a literary work: '
        'ask for the intended work/textbook/author rather than guessing a literary identity. '
        'If it has multiple materially different meanings or the learner says they cannot decide what they mean, '
        'return {"clarify":true,"question":"one short question","options":["specific interpretation A",'
        '"specific interpretation B"],"others":[],"multi":false}. Supply 2-5 meaningful choices. '
        'Do not answer the question. Do not provide explanation outside JSON. '
        'Use Bengali for Bengali, English, mixed or romanized Bengali; otherwise the learner language. '
        'Ignore the stock prefix "বিস্তারিত আলোচনা করুন:" or "Discuss Details on". '
        'Use the conversation to interpret a selection or clarification of an earlier question; '
        'a resolved selection should return {"clarify":false}. Never repeat an already resolved question.'
    )
    model = payload['model'] if payload['model'] != 'auto' else getattr(settings, 'TUTOR_FAST_MODEL', FAST)
    try:
        raw = complete({
            'model': model, 'messages': [{'role': 'system', 'content': policy}] + [m for m in payload['messages'] if m['role'] != 'system'][-4:],
            'file_context': [], 'max_tokens': 384, 'stream': False}, base_url, timeout=30)
        if not isinstance(raw, str) or unusable(raw):
            return None
        start, end = raw.find('{'), raw.rfind('}')
        data = json.loads(raw[start:end + 1])
        if data.get('clarify') is not True:
            return None
        question, options = data.get('question'), data.get('options')
        if (not isinstance(question, str) or not question.strip() or len(question) > 500
                or not isinstance(options, list) or not 2 <= len(options) <= 5
                or any(not isinstance(x, str) or not x.strip() or len(x) > 250 for x in options)):
            return None
        others = data.get('others', [])
        others = [x for x in others if isinstance(x, str) and x.strip() and len(x) <= 250][:5] if isinstance(others, list) else []
        card = {'question': question.strip(), 'options': options, 'others': others, 'multi': data.get('multi') is True}
        return '```cheradip-ask\n' + json.dumps(card, ensure_ascii=False) + '\n```'
    except (requests.RequestException, ValueError, AttributeError, TypeError):
        return None  # Ordinary answering remains available if the intent check fails.
