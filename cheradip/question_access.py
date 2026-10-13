"""Subject-qualified, server-priced Study entitlements."""
import json

from django.db import connections, transaction
from .models import Customer
from .package_service import active_subscriptions, subsource_allowed
from .subject_question_tables import subject_question_table_name
from .wallet_service import deduct_wallet_coins, wallet_coins

KEYS = 'unlocked_question_keys'
CLAIMS = 'legacy_question_unlock_claims'
SECRET_FIELDS = ('answer', 'explanation', 'explanation2', 'explanation3')


def question_key(db, table, qid):
    return json.dumps([db, table, str(qid)], ensure_ascii=False, separators=(',', ':'))


def package_covers(packages, question):
    return any(subsource_allowed(row.plan.track, question.get('subsource')) for row in packages)


def bind_legacy(settings, db, table, questions):
    keys = set(settings.get(KEYS) or [])
    claims = dict(settings.get(CLAIMS) or {})
    legacy = {str(qid) for qid in settings.get('unlocked_question_qids', [])}
    for q in questions:
        qid = str(q.get('qid') or q.get('id') or '')
        key = question_key(db, table, qid)
        if qid in legacy and qid not in claims:
            claims[qid] = key
            keys.add(key)
    settings[KEYS], settings[CLAIMS] = sorted(keys), claims
    return keys


def protect_questions(user, db, table, questions):
    packages = active_subscriptions(user, audience='student') if getattr(user, 'is_authenticated', False) else []
    keys = set()
    if getattr(user, 'is_authenticated', False):
        with transaction.atomic():
            locked = Customer.objects.select_for_update().get(pk=user.pk)
            data = dict(locked.settings or {})
            before = json.dumps(data, sort_keys=True)
            keys = bind_legacy(data, db, table, questions)
            if json.dumps(data, sort_keys=True) != before:
                locked.settings = data
                locked.save(update_fields=['settings'])
            user.settings = data
    staff = getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False)
    for q in questions:
        key = question_key(db, table, q.get('qid') or q.get('id'))
        q.update(access_key=key, table=table, db_alias=db, purchased=key in keys, package_access=package_covers(packages, q))
        if not (staff or q['purchased'] or q['package_access']):
            for field in SECRET_FIELDS:
                if field in q:
                    q[field] = ''
            q['answer_locked'] = True
    return questions


def load_unlock_item(item):
    level, cls, subject = (str(item.get(key) or '').strip() for key in ('level_tr', 'class_level', 'subject_tr'))
    if not all((level, cls, subject)):
        raise ValueError('Subject context is required. Refresh the question page before unlocking.')
    db = str(item.get('db_alias') or ('honours' if 'honour' in level.lower() else 'job' if 'job' in level.lower() else 'hsc'))
    if db not in {'hsc', 'honours', 'job'} or db not in connections:
        raise ValueError('Unsupported question database.')
    table = subject_question_table_name(level, cls, subject)
    qid = str(item.get('qid') or '').strip()
    with connections[db].cursor() as cursor:
        if table not in connections[db].introspection.table_names(cursor):
            raise ValueError('Subject table not found.')
        cols = {c.name for c in connections[db].introspection.get_table_description(cursor, table)}
        pk = 'qid' if 'qid' in cols else 'id'
        cursor.execute(f'SELECT * FROM `{table.replace(chr(96), chr(96)*2)}` WHERE `{pk}` = %s LIMIT 1', [qid])
        row = cursor.fetchone()
        if not row:
            raise ValueError('Question not found.')
        question = dict(zip([col[0] for col in cursor.description], row))
    question['qid'] = qid
    question.update(level_tr=level, class_level=cls, subject_tr=subject, db_alias=db, table=table)
    return db, table, question


def unlock_items(customer, items):
    loaded = [load_unlock_item(item) for item in items if isinstance(item, dict)]
    if not loaded:
        raise ValueError('No questions to unlock.')
    packages = active_subscriptions(customer, audience='student')
    with transaction.atomic():
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        data = dict(customer.settings or {})
        keys = set(data.get(KEYS) or [])
        result, chargeable = [], {}
        for db, table, q in loaded:
            keys.update(bind_legacy(data, db, table, [q]))
            key = question_key(db, table, q['qid'])
            q['access_key'] = key
            q['package_access'] = package_covers(packages, q)
            if key not in keys and not q['package_access']:
                kind = str(q.get('type') or '').casefold()
                chargeable[key] = 50 if kind == 'cq' or 'সৃজনশীল' in kind or 'creative' in kind else 10
            result.append(q)
        debit = sum(chargeable.values())
        if debit > wallet_coins(customer):
            return {'success': False, 'detail': 'Insufficient coins for unlock', 'remaining': wallet_coins(customer), 'debited': 0}, 400
        if debit:
            deduct_wallet_coins(customer, debit)
        data['balance'] = wallet_coins(customer)
        keys.update(chargeable)
        data[KEYS] = sorted(keys)
        customer.settings = data
        customer.save(update_fields=['settings'])
        for q in result:
            q['purchased'] = q['access_key'] in keys
        return {'success': True, 'remaining': wallet_coins(customer), 'debited': debit,
                'unlocked_keys': sorted(keys), 'unlocked_qids': [q['qid'] for q in result],
                'package_access': all(q['package_access'] for q in result), 'questions': result}, 200
