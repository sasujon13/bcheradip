from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.db.models import Sum

from .membership import discounted_price, public_rules, refresh_membership
from .models import PackagePlan, PackageSubscription, ReferralCommission
from .package_service import activate_plan, current_subscription, subscription_payload
from .views import BearerTokenAuthentication


def _progress_payload(progress):
    return {
        'accountType': progress.account_type,
        'base': progress.base,
        'badge': progress.badge,
        'metricName': progress.metric_name,
        'metricCount': progress.metric_count,
        'rawMetricCount': progress.raw_metric_count,
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
        active = None
        discount = 0
        if getattr(request.user, 'is_authenticated', False):
            active = current_subscription(request.user)
            progress = refresh_membership(request.user)
            account_type = progress.account_type
            discount = progress.discount_percent
        plans = []
        for plan in PackagePlan.objects.filter(is_active=True):
            renewal = discounted_price(plan.price, discount)
            plans.append({
                'code': plan.code, 'name': plan.name, 'durationMonths': plan.duration_months,
                'track': plan.track, 'listPrice': float(plan.list_price), 'price': float(plan.price),
                'discountPercent': discount, 'payableAmount': float(plan.price),
                'renewalAmount': float(renewal), 'currency': plan.currency,
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
            'activeSubscription': subscription_payload(active),
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
        try:
            subscription, remaining, created, message = activate_plan(
                request.user, plan, request.data.get('paymentReference')
            )
        except ValueError as exc:
            if str(exc).startswith('insufficient:'):
                _, required, required_coins, balance = str(exc).split(':', 3)
                return Response({
                    'error': 'Insufficient wallet balance. Please recharge and try again.',
                    'code': 'insufficient_balance', 'required': float(required),
                    'requiredCoins': int(required_coins), 'remaining': int(balance),
                    'shortfallCoins': max(0, int(required_coins) - int(balance)),
                }, status=status.HTTP_400_BAD_REQUEST)
            raise
        progress = refresh_membership(request.user)
        return Response({
            'id': subscription.id, 'status': subscription.status, 'planCode': plan.code,
            'payableAmount': float(subscription.payable_amount),
            'remainingBalance': remaining,
            'message': message,
            'progress': _progress_payload(progress),
            'activeSubscription': subscription_payload(subscription),
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PackageStatusView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active = current_subscription(request.user)
        progress = refresh_membership(request.user)
        active_payload = subscription_payload(active, mark_warning=True)
        next_target = progress.next_metric_target
        completed = progress.metric_count
        remaining = max(0, (next_target or completed) - completed)
        return Response({
            'active': bool(active), 'activeSubscription': active_payload,
            'progress': _progress_payload(progress), 'base': progress.base,
            'badge': progress.badge, 'metricName': progress.metric_name,
            'completedTasks': completed, 'remainingTasks': remaining,
            'nextBase': (f"{'E' if progress.account_type == 'Student' else 'Q'} > {next_target - 1}" if next_target else None),
            'passingRate': float(progress.passing_rate),
            'questionTrack': active.plan.track if active and progress.account_type == 'Student' else None,
            # Use the same public, browser-safe media path as the upload endpoint. Avoid
            # leaking an internal proxy host through request.build_absolute_uri().
            'profileImageUrl': '/manage' + request.user.profile_image.url if request.user.profile_image else None,
        })


class ReferralSummaryView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        current_subscription(request.user)
        progress = refresh_membership(request.user)
        earnings = ReferralCommission.objects.filter(referrer=request.user).select_related('referred_customer', 'subscription__plan')
        total = earnings.aggregate(total=Sum('commission_coins'))['total'] or 0
        return Response({
            'reference': request.user.username,
            'referencePath': f'/auth?reference={request.user.username}',
            'referenceValuePercent': progress.reference_value_percent,
            'referredUsers': request.user.referred_customers.count(),
            'totalCommissionCoins': int(total),
            'earnings': [{
                'id': row.id,
                'customer': row.referred_customer.fullName,
                'mobile': row.referred_customer.username,
                'plan': row.subscription.plan.name,
                'grossAmount': float(row.gross_amount),
                'referenceValuePercent': row.reference_value_percent,
                'commissionCoins': row.commission_coins,
                'createdAt': row.created_at.isoformat(),
            } for row in earnings[:50]],
        })
