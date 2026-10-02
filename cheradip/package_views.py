from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from .membership import add_months, discounted_price, public_rules, refresh_membership
from .models import Customer, PackagePlan, PackageSubscription
from .views import BearerTokenAuthentication


def _progress_payload(progress):
    return {
        'accountType': progress.account_type,
        'badge': progress.badge,
        'metricName': progress.metric_name,
        'metricCount': progress.metric_count,
        'recentMetricCount': progress.recent_metric_count,
        'passingRate': float(progress.passing_rate),
        'discountPercent': progress.discount_percent,
        'referenceValuePercent': progress.reference_value_percent,
        'cqRate': float(progress.cq_rate) if progress.cq_rate is not None else None,
        'mcqRate': float(progress.mcq_rate) if progress.mcq_rate is not None else None,
        'maintenanceMet': progress.maintenance_met,
        'nextBadge': progress.next_badge or None,
        'nextMetricTarget': progress.next_metric_target,
    }


class PackageListView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        account_type = request.query_params.get('account_type') or 'Student'
        progress = None
        discount = 0
        if getattr(request.user, 'is_authenticated', False):
            progress = refresh_membership(request.user)
            account_type = progress.account_type
            discount = progress.discount_percent
        plans = []
        for plan in PackagePlan.objects.filter(is_active=True):
            payable = discounted_price(plan.price, discount)
            plans.append({
                'code': plan.code, 'name': plan.name, 'durationMonths': plan.duration_months,
                'track': plan.track, 'listPrice': float(plan.list_price), 'price': float(plan.price),
                'discountPercent': discount, 'payableAmount': float(payable), 'currency': plan.currency,
                'features': plan.features if isinstance(plan.features, list) else [],
            })
        subscriptions = []
        if progress:
            subscriptions = [{
                'id': row.id, 'planCode': row.plan.code, 'status': row.status,
                'payableAmount': float(row.payable_amount),
                'startsAt': row.starts_at.isoformat() if row.starts_at else None,
                'endsAt': row.ends_at.isoformat() if row.ends_at else None,
            } for row in PackageSubscription.objects.filter(customer=request.user).select_related('plan')[:20]]
        return Response({
            'plans': plans,
            'rules': public_rules(account_type if account_type in {'Student', 'Teacher', 'JobSeeker'} else 'Student'),
            'maintenance': {'target': 50, 'days': 90},
            'progress': _progress_payload(progress) if progress else None,
            'subscriptions': subscriptions,
        })


class PackageSubscribeView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = str(request.data.get('planCode') or '').strip()
        try:
            plan = PackagePlan.objects.get(code=code, is_active=True)
        except PackagePlan.DoesNotExist:
            return Response({'error': 'Package plan was not found.'}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=request.user.pk)
            progress = refresh_membership(customer)
            payable = discounted_price(plan.price, progress.discount_percent)
            now = timezone.now()
            existing = PackageSubscription.objects.filter(
                customer=customer,
                plan=plan,
                status__in=['pending', 'active'],
            ).order_by('-created_at').first()
            if existing and existing.status == 'active' and (not existing.ends_at or existing.ends_at > now):
                return Response({
                    'id': existing.id, 'status': existing.status, 'planCode': plan.code,
                    'payableAmount': float(existing.payable_amount),
                    'message': 'This package is already active.',
                    'remainingBalance': int((customer.settings or {}).get('balance', 0) or 0),
                    'progress': _progress_payload(progress),
                })
            customer_settings = customer.settings.copy() if isinstance(customer.settings, dict) else {}
            try:
                balance = int(customer_settings.get('balance', 0) or 0)
            except (TypeError, ValueError):
                balance = 0
            if payable > balance:
                return Response({
                    'error': 'Insufficient wallet balance.',
                    'code': 'insufficient_balance',
                    'required': float(payable),
                    'remaining': balance,
                    'shortfall': float(payable - balance),
                }, status=status.HTTP_400_BAD_REQUEST)
            remaining = balance - int(payable)
            customer_settings['balance'] = remaining
            customer.settings = customer_settings
            customer.save(update_fields=['settings'])
            subscription = existing if existing and existing.status == 'pending' else PackageSubscription(customer=customer, plan=plan)
            subscription.status = 'active'
            subscription.plan_price = plan.price
            subscription.badge_discount_percent = progress.discount_percent
            subscription.payable_amount = payable
            subscription.payment_reference = str(request.data.get('paymentReference') or '').strip()[:80]
            subscription.starts_at = now
            subscription.ends_at = add_months(now, plan.duration_months)
            subscription.save()
            progress = refresh_membership(customer)
        return Response({
            'id': subscription.id, 'status': subscription.status, 'planCode': plan.code,
            'payableAmount': float(subscription.payable_amount),
            'remainingBalance': remaining,
            'message': 'Package activated successfully.',
            'progress': _progress_payload(progress),
        }, status=status.HTTP_201_CREATED)
