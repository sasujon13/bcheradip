"""Validate streamed model text before publishing it to the tutor."""
import codecs
import json
import re


class UnusableReply(ValueError):
    pass


def unusable(text):
    if re.search(r'@{12,}|\ufffd{6,}|([^\s])\1{39,}', text):
        return True
    # Ignore code: repeated statements/rows can be intentional there. Catch prose
    # loops in Bengali as well as Latin scripts, including numbered paragraphs.
    prose = re.sub(r'```[\s\S]*?(?:```|$)', '', text)
    sentences = re.split(r'[।!?\n]+|\.(?:\s|$)', prose)
    counts = {}
    for sentence in sentences:
        normalized = re.sub(r'\s+', ' ', sentence).strip(' \t*-0123456789০১২৩৪৫৬৭৮৯.)(').casefold()
        if len(normalized) >= 35:
            counts[normalized] = counts.get(normalized, 0) + 1
            if counts[normalized] >= 3:
                return True
    compact = ''.join(text.split())
    return len(compact) >= 32 and not any(c.isalnum() for c in compact) and len(set(compact)) <= 3


def checked_chunks(upstream):
    """Hold back a small tail, including split SSE frames and split UTF-8 tokens."""
    decoder = codecs.getincrementaldecoder('utf-8')()
    buffer, full, sent = '', '', 0
    def lines(chunk, final=False):
        nonlocal buffer
        buffer += decoder.decode(chunk, final=final)
        parts = buffer.split('\n'); buffer = parts.pop()
        if final and buffer.strip():
            parts.append(buffer); buffer = ''
        return parts
    def consume(line):
        nonlocal full
        if not line.startswith('data:'):
            return
        value = line[5:].strip()
        if not value or value == '[DONE]':
            return
        data = json.loads(value)
        if data.get('error'):
            raise ValueError('Home AI interrupted the response.')
        content = data.get('content', '')
        if not isinstance(content, str):
            raise ValueError('Invalid Home AI response.')
        full += content
        if unusable(full):
            raise UnusableReply('Model returned repeated or unreadable symbols.')
    for chunk in upstream.iter_content(chunk_size=256):
        for line in lines(chunk):
            consume(line)
        # Keep structured clarification private until complete; never flash JSON
        # or replace a selectable card on every streaming token.
        if full.lstrip().startswith('```') or '```cheradip-ask'.startswith(full.lstrip()):
            if full.lstrip().startswith('```cheradip-ask'):
                match = re.search(r'```cheradip-ask\s*\n([\s\S]*?)```', full)
                if match:
                    try:
                        ask = json.loads(match.group(1))
                        valid = (isinstance(ask, dict) and isinstance(ask.get('question'), str)
                                 and ask['question'].strip() and isinstance(ask.get('options'), list)
                                 and 2 <= len(ask['options']) <= 5
                                 and all(isinstance(x, str) and x.strip() for x in ask['options']))
                    except (ValueError, TypeError):
                        valid = False
                    if not valid:
                        raise UnusableReply('Invalid clarification options.')
                    yield match.group(0)
                    return  # A clarification must stop and wait for the learner.
                continue
            if len(full.lstrip()) < len('```cheradip-ask'):
                continue
        safe_end = max(sent, len(full) - 64)
        if safe_end > sent:
            yield full[sent:safe_end]; sent = safe_end
    for line in lines(b'', final=True):
        consume(line)
    if not full.strip():
        raise UnusableReply('Model returned an empty response.')
    if full.lstrip().startswith('```cheradip-ask'):
        raise UnusableReply('Incomplete clarification options.')
    if sent < len(full):
        yield full[sent:]
