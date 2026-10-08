import calendar

from django.db import migrations
from django.db.models import Q
from django.utils import timezone


FREE_CODES = (
    'free-academic',
    'free-admission',
    'teacher-free-academic',
    'teacher-free-admission',
)


def add_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def activate_default_free_packages(apps, schema_editor):
    Customer = apps.get_model('cheradip', 'Customer')
    Plan = apps.get_model('cheradip', 'PackagePlan')
    Subscription = apps.get_model('cheradip', 'PackageSubscription')
    now = timezone.now()

    plans = {plan.code: plan for plan in Plan.objects.filter(code__in=FREE_CODES)}
    Plan.objects.filter(name='Free').update(duration_months=36)

    for subscription in Subscription.objects.filter(
        plan__name='Free', status__in=['active', 'grace'], starts_at__isnull=False,
    ).select_related('plan'):
        ends_at = add_months(subscription.starts_at, 36)
        Subscription.objects.filter(pk=subscription.pk).update(
            ends_at=ends_at, next_renewal_at=ends_at, auto_renew=False,
        )

    for customer in Customer.objects.all().iterator():
        for code in FREE_CODES:
            plan = plans.get(code)
            if not plan:
                continue
            if Subscription.objects.filter(
                customer=customer,
                plan__audience=plan.audience,
                plan__track=plan.track,
            ).filter(
                Q(payment_reference=f'default-free:{plan.audience}:{plan.track}') |
                Q(plan__name='Free')
            ).exists():
                continue
            ends_at = add_months(now, 36)
            Subscription.objects.create(
                customer=customer,
                plan=plan,
                status='active',
                plan_price=0,
                badge_discount_percent=0,
                payable_amount=0,
                question_limit_snapshot=plan.question_limit,
                questions_used=0,
                payment_reference=f'default-free:{plan.audience}:{plan.track}',
                starts_at=now,
                ends_at=ends_at,
                next_renewal_at=ends_at,
                auto_renew=False,
            )


class Migration(migrations.Migration):
    dependencies = [('cheradip', '0017_rewards_wallet_withdrawals')]

    operations = [
        migrations.RunPython(activate_default_free_packages, migrations.RunPython.noop),
    ]
