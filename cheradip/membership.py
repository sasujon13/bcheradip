"""Membership badges, activity progress, and personalized package prices."""
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import CreatedQuestionSet, MembershipProgress, PackageSubscription


STUDENT_RULES = [
    {'badge': 'Gold', 'target': 100, 'passing_rate': 50, 'discount': 10, 'rv': 25},
    {'badge': 'Gold+', 'target': 200, 'passing_rate': 65, 'discount': 20, 'rv': 25},
    {'badge': 'Platinum', 'target': 300, 'passing_rate': 80, 'discount': 30, 'rv': 30},
    {'badge': 'Platinum+', 'target': 400, 'passing_rate': 90, 'discount': 40, 'rv': 30},
    {'badge': 'Titanium', 'target': 500, 'passing_rate': 95, 'discount': 50, 'rv': 30},
]
TEACHER_RULES = [
    {'badge': 'Gold', 'target': 100, 'discount': 10, 'rv': 30, 'cq_rate': '1.40', 'mcq_rate': '0.23'},
    {'badge': 'Gold+', 'target': 200, 'discount': 20, 'rv': 35, 'cq_rate': '1.30', 'mcq_rate': '0.21'},
    {'badge': 'Platinum', 'target': 300, 'discount': 30, 'rv': 40, 'cq_rate': '1.20', 'mcq_rate': '0.19'},
    {'badge': 'Platinum+', 'target': 400, 'discount': 40, 'rv': 45, 'cq_rate': '1.10', 'mcq_rate': '0.17'},
    {'badge': 'Titanium', 'target': 500, 'discount': 50, 'rv': 50, 'cq_rate': '1.00', 'mcq_rate': '0.15'},
]
# Job seekers use the same lifetime unique-question thresholds as teachers.
JOB_SEEKER_RULES = [
    {key: value for key, value in rule.items() if key not in {'cq_rate', 'mcq_rate'}}
    for rule in TEACHER_RULES
]
MAINTENANCE_TARGET = 50
MAINTENANCE_DAYS = 90


def add_months(value, months):
    month_index = value.month - 1 + int(months)
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month, day=min(value.day, monthrange(year, month)[1]))


def _active_plan(customer, audience, now=None):
    now = now or timezone.now()
    row = PackageSubscription.objects.filter(
        customer=customer,
        plan__audience=audience,
        status__in=['active', 'grace'],
        starts_at__lte=now,
    ).select_related('plan').order_by('-plan__sort_order', '-starts_at', '-id').first()
    return row.plan if row else None


def _question_key(question):
    if not isinstance(question, dict):
        return ''
    qid = str(question.get('qid') or question.get('id') or '').strip()
    text = ' '.join(str(question.get('question') or '').split()).casefold()
    if qid:
        return f'id:{qid}|text:{text}'
    return f'text:{text}' if text else ''


def _teacher_metrics(customer, now):
    all_keys, recent_keys = set(), set()
    cutoff = now - timedelta(days=MAINTENANCE_DAYS)
    for created_at, questions in CreatedQuestionSet.objects.filter(customer=customer).values_list('created_at', 'questions'):
        keys = {_question_key(row) for row in questions if isinstance(row, dict)} if isinstance(questions, list) else set()
        keys.discard('')
        all_keys.update(keys)
        if created_at and created_at >= cutoff:
            recent_keys.update(keys)
    return len(all_keys), len(recent_keys), Decimal('0')


def _exam_metrics(customer, now):
    settings = customer.settings if isinstance(customer.settings, dict) else {}
    rows = settings.get('student_exam_results') if isinstance(settings.get('student_exam_results'), list) else []
    stored_total = int(settings.get('membership_exam_lifetime_count') or 0)
    stored_passed = int(settings.get('membership_exam_passed_count') or 0)
    total = max(stored_total, len(rows))
    row_passed = sum(1 for row in rows if isinstance(row, dict) and float(row.get('score') or 0) >= 40)
    passed = max(stored_passed, row_passed)
    passing_rate = (Decimal(passed) * Decimal('100') / Decimal(total)) if total else Decimal('0')
    cutoff = now - timedelta(days=MAINTENANCE_DAYS)
    recent = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        attempted_at = parse_datetime(str(row.get('at') or ''))
        if attempted_at:
            if timezone.is_naive(attempted_at):
                attempted_at = timezone.make_aware(attempted_at, timezone.get_default_timezone())
            if attempted_at >= cutoff:
                recent += 1
    return total, recent, passing_rate.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def public_rules(account_type):
    if account_type in {'Teacher', 'JobSeeker'}:
        rules = TEACHER_RULES
        return [
            {'base': 'Free', 'badge': 'None', 'cqRate': None, 'mcqRate': None, 'discountPercent': 0, 'referenceValuePercent': 0},
            {'base': 'New', 'badge': 'Star', 'cqRate': 1.50 if account_type == 'Teacher' else None, 'mcqRate': .25 if account_type == 'Teacher' else None, 'discountPercent': 0, 'referenceValuePercent': 20},
            {'base': 'Premium', 'badge': 'Silver', 'cqRate': 1.50 if account_type == 'Teacher' else None, 'mcqRate': .25 if account_type == 'Teacher' else None, 'discountPercent': 0, 'referenceValuePercent': 25},
            *[{'base': f"Q > {rule['target'] - 1}", 'badge': rule['badge'], 'cqRate': float(rule['cq_rate']) if account_type == 'Teacher' else None, 'mcqRate': float(rule['mcq_rate']) if account_type == 'Teacher' else None, 'discountPercent': rule['discount'], 'referenceValuePercent': rule['rv']} for rule in rules],
        ]
    rules = STUDENT_RULES
    return [
        {'base': 'Free', 'badge': 'None', 'passingRate': None, 'discountPercent': 0, 'referenceValuePercent': 0},
        {'base': 'New', 'badge': 'Star', 'passingRate': None, 'discountPercent': 0, 'referenceValuePercent': 20},
        {'base': 'Premium', 'badge': 'Silver', 'passingRate': None, 'discountPercent': 0, 'referenceValuePercent': 25},
        *[{'base': f"E > {rule['target'] - 1}", 'badge': rule['badge'], 'passingRate': rule['passing_rate'], 'discountPercent': rule['discount'], 'referenceValuePercent': rule['rv']} for rule in rules],
    ]


def refresh_membership(customer, now=None, audience=None):
    now = now or timezone.now()
    audience = audience or ('student' if customer.acctype == 'Student' else 'teacher')
    account_type = (
        'Student' if audience == 'student'
        else (customer.acctype if customer.acctype in {'Teacher', 'JobSeeker'} else 'Teacher')
    )
    plan = _active_plan(customer, audience, now)
    paid = bool(plan and plan.price > 0)
    starter = bool(paid and (plan.sort_order == 1 or plan.name.casefold() == 'starter'))
    if account_type in {'Teacher', 'JobSeeker'}:
        raw_metric_count, recent_count, passing_rate = _teacher_metrics(customer, now)
        rules = TEACHER_RULES
        metric_name = 'questions_created'
    else:
        raw_metric_count, recent_count, passing_rate = _exam_metrics(customer, now)
        rules = STUDENT_RULES
        metric_name = 'exams_attended'

    previous = MembershipProgress.objects.filter(customer=customer, audience=audience).first()
    raw_metric_count = max(raw_metric_count, previous.raw_metric_count if previous else 0)
    metric_offset = min(previous.metric_offset if previous else 0, raw_metric_count)
    penalty_active = bool(previous and previous.maintenance_penalty_active)
    metric_count = max(0, raw_metric_count - metric_offset)

    matched = None
    for rule in rules:
        rate_ok = account_type != 'Student' or passing_rate >= Decimal(str(rule['passing_rate']))
        if metric_count >= rule['target'] and rate_ok:
            matched = rule
    maintenance_met = matched is None or recent_count >= MAINTENANCE_TARGET
    if paid and matched and not maintenance_met and not penalty_active:
        matched_index = rules.index(matched)
        previous_target = rules[matched_index - 1]['target'] if matched_index > 0 else 0
        metric_offset += max(0, metric_count - previous_target)
        metric_count = previous_target
        penalty_active = True
        matched = None
        for rule in rules:
            rate_ok = account_type != 'Student' or passing_rate >= Decimal(str(rule['passing_rate']))
            if metric_count >= rule['target'] and rate_ok:
                matched = rule
    elif recent_count >= MAINTENANCE_TARGET:
        penalty_active = False

    effective = matched if paid else None
    if effective:
        badge, discount, rv = effective['badge'], effective['discount'], effective['rv']
        base = f"{'E' if account_type == 'Student' else 'Q'} > {effective['target'] - 1}"
    elif starter:
        badge, discount, rv = 'Star', 0, 20
        base = 'New'
    elif paid:
        badge, discount, rv = 'Silver', 0, 25
        base = 'Premium'
    else:
        badge, discount, rv = 'None', 0, 0
        base = 'Free'
    cq_rate = Decimal(effective.get('cq_rate', '1.50')) if account_type == 'Teacher' and effective else (Decimal('1.50') if account_type == 'Teacher' else None)
    mcq_rate = Decimal(effective.get('mcq_rate', '0.25')) if account_type == 'Teacher' and effective else (Decimal('0.25') if account_type == 'Teacher' else None)
    next_rule = next((rule for rule in rules if metric_count < rule['target'] or (account_type == 'Student' and passing_rate < Decimal(str(rule['passing_rate'])))), None)
    progress, _ = MembershipProgress.objects.update_or_create(customer=customer, audience=audience, defaults={
        'account_type': account_type,
        'base': base,
        'badge': badge,
        'metric_name': metric_name,
        'metric_count': metric_count,
        'raw_metric_count': raw_metric_count,
        'metric_offset': metric_offset,
        'recent_metric_count': recent_count,
        'passing_rate': passing_rate,
        'discount_percent': discount,
        'reference_value_percent': rv,
        'cq_rate': cq_rate,
        'mcq_rate': mcq_rate,
        'maintenance_met': maintenance_met,
        'maintenance_penalty_active': penalty_active,
        'next_badge': next_rule['badge'] if next_rule else '',
        'next_metric_target': next_rule['target'] if next_rule else None,
    })
    return progress


def discounted_price(price, discount_percent):
    value = Decimal(price) * (Decimal('100') - Decimal(discount_percent)) / Decimal('100')
    # The existing Cheradip wallet stores whole coins/Taka, so package charges
    # must use the same unit shown in the UI and deducted from the wallet.
    return value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
