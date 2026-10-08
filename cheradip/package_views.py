from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import quote

from .membership import discounted_price, public_rules, refresh_membership
from .models import (
    PackagePlan, PackageSubscription, ReferralCommission,
    RewardsWallet, WithdrawalRequest,
)
from .package_service import active_subscriptions, activate_plan, current_subscription, subscription_payload
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


def _rewards_wallet_payload(customer):
    wallet, _ = RewardsWallet.objects.get_or_create(customer=customer)
    settings = customer.settings if isinstance(customer.settings, dict) else {}
    try:
        coins = max(0, int(settings.get('balance', 0) or 0))
    except (TypeError, ValueError):
        coins = 0
    return {
        'name': 'Cheradip Rewards Wallet',
        'coinBalance': coins,
        'availableTaka': float(wallet.available_taka),
        'lifetimeEarnedTaka': float(wallet.lifetime_earned_taka),
        'lifetimeWithdrawnTaka': float(wallet.lifetime_withdrawn_taka),
        'minimumWithdrawalTaka': 100,
    }


def _withdrawal_payload(row):
    return {
        'id': row.id,
        'method': row.method,
        'methodLabel': row.get_method_display(),
        'accountName': row.account_name,
        'accountNumber': row.account_number,
        'amountTaka': float(row.amount_taka),
        'status': row.status,
        'statusLabel': row.get_status_display(),
        'adminNote': row.admin_note,
        'requestedAt': row.requested_at.isoformat(),
        'processedAt': row.processed_at.isoformat() if row.processed_at else None,
    }


class PackageListView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        account_type = request.query_params.get('account_type') or 'Student'
        progress = None
        student_progress = None
        teacher_progress = None
        active = None
        active_rows = []
        discount = 0
        if getattr(request.user, 'is_authenticated', False):
            active_rows = active_subscriptions(request.user)
            primary_audience = 'student' if request.user.acctype == 'Student' else 'teacher'
            active = next((row for row in active_rows if row.plan.audience == primary_audience), None)
            progress = refresh_membership(request.user)
            student_progress = refresh_membership(request.user, audience='student')
            teacher_progress = refresh_membership(request.user, audience='teacher')
            account_type = progress.account_type
            discount = progress.discount_percent
        plans = []
        for plan in PackagePlan.objects.filter(is_active=True):
            audience_progress = teacher_progress if plan.audience == 'teacher' else student_progress
            plan_discount = audience_progress.discount_percent if audience_progress else discount
            renewal = discounted_price(plan.price, plan_discount)
            plans.append({
                'code': plan.code, 'name': plan.name, 'durationMonths': plan.duration_months,
                'audience': plan.audience, 'track': plan.track,
                'listPrice': float(plan.list_price), 'price': float(plan.price),
                'discountPercent': plan_discount, 'payableAmount': float(plan.price),
                'renewalAmount': float(renewal), 'currency': plan.currency,
                'questionLimit': plan.question_limit,
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
            'studentProgress': _progress_payload(student_progress) if student_progress else None,
            'teacherProgress': _progress_payload(teacher_progress) if teacher_progress else None,
            'activeSubscription': subscription_payload(active),
            'activeSubscriptions': [subscription_payload(row) for row in active_rows],
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
        progress = refresh_membership(request.user, audience=plan.audience)
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
        active_rows = active_subscriptions(request.user)
        primary_audience = 'student' if request.user.acctype == 'Student' else 'teacher'
        active = next((row for row in active_rows if row.plan.audience == primary_audience), None)
        progress = refresh_membership(request.user)
        student_progress = refresh_membership(request.user, audience='student')
        teacher_progress = refresh_membership(request.user, audience='teacher')
        active_payloads = [subscription_payload(row, mark_warning=True) for row in active_rows]
        active_payload = next((payload for payload in active_payloads if active and payload['id'] == active.id), None)
        warnings = [payload['warning'] for payload in active_payloads if payload.get('warning')]
        next_target = progress.next_metric_target
        completed = progress.metric_count
        remaining = max(0, (next_target or completed) - completed)
        return Response({
            'active': bool(active), 'activeSubscription': active_payload,
            'activeSubscriptions': active_payloads,
            'warnings': warnings,
            'progress': _progress_payload(progress), 'base': progress.base,
            'studentProgress': _progress_payload(student_progress),
            'teacherProgress': _progress_payload(teacher_progress) if teacher_progress else None,
            'badge': progress.badge, 'metricName': progress.metric_name,
            'completedTasks': completed, 'remainingTasks': remaining,
            'nextBase': (f"{'E' if progress.account_type == 'Student' else 'Q'} > {next_target - 1}" if next_target else None),
            'passingRate': float(progress.passing_rate),
            'questionTrack': (
                'combined' if progress.account_type == 'Student' and (
                    any(row.plan.audience == 'student' and row.plan.track == 'combined' for row in active_rows) or
                    {'academic', 'admission'}.issubset({
                        row.plan.track for row in active_rows if row.plan.audience == 'student'
                    })
                ) else next((row.plan.track for row in active_rows if row.plan.audience == 'student'), None)
            ),
            # Use the same public, browser-safe media path as the upload endpoint. Avoid
            # leaking an internal proxy host through request.build_absolute_uri().
            'profileImageUrl': '/manage' + request.user.profile_image.url if request.user.profile_image else None,
            'wallet': _rewards_wallet_payload(request.user),
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
            # Username is the stored reference. Quote it so leading country-code
            # plus signs and other valid characters survive the query string exactly.
            'referencePath': f'/auth?reference={quote(request.user.username, safe="")}',
            'referenceValuePercent': progress.reference_value_percent,
            'referredUsers': request.user.referred_customers.count(),
            'totalCommissionCoins': int(total),
            'wallet': _rewards_wallet_payload(request.user),
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


class RewardsWalletView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        requests = WithdrawalRequest.objects.filter(customer=request.user)[:30]
        return Response({
            'wallet': _rewards_wallet_payload(request.user),
            'methods': [
                {'value': value, 'label': label}
                for value, label in WithdrawalRequest.METHOD_CHOICES
            ],
            'withdrawals': [_withdrawal_payload(row) for row in requests],
        })

    def post(self, request):
        method = str(request.data.get('method') or '').strip().lower()
        allowed_methods = dict(WithdrawalRequest.METHOD_CHOICES)
        if method not in allowed_methods:
            return Response({'error': 'Select a valid withdrawal method.'}, status=status.HTTP_400_BAD_REQUEST)
        account_number = str(request.data.get('accountNumber') or '').strip()
        account_name = str(request.data.get('accountName') or '').strip()
        if len(account_number) < 6 or len(account_number) > 64:
            return Response({'error': 'Enter a valid account number.'}, status=status.HTTP_400_BAD_REQUEST)
        if method in {'dbbl', 'sonali'} and not account_name:
            return Response({'error': 'Account holder name is required for bank withdrawals.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            amount = Decimal(str(request.data.get('amountTaka') or '')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP,
            )
        except (InvalidOperation, TypeError, ValueError):
            return Response({'error': 'Enter a valid withdrawal amount.'}, status=status.HTTP_400_BAD_REQUEST)
        if amount < Decimal('100.00'):
            return Response({'error': 'Minimum withdrawal amount is Tk 100.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            wallet, _ = RewardsWallet.objects.select_for_update().get_or_create(customer=request.user)
            if amount > wallet.available_taka:
                return Response({
                    'error': 'Requested amount exceeds your available reference balance.',
                    'availableTaka': float(wallet.available_taka),
                }, status=status.HTTP_400_BAD_REQUEST)
            before = wallet.available_taka
            wallet.available_taka -= amount
            wallet.save(update_fields=['available_taka', 'updated_at'])
            row = WithdrawalRequest.objects.create(
                customer=request.user, method=method, account_name=account_name,
                account_number=account_number, amount_taka=amount,
                balance_before_taka=before, balance_after_taka=wallet.available_taka,
            )
        return Response({
            'message': 'Withdrawal request submitted for manual payment and approval.',
            'withdrawal': _withdrawal_payload(row),
            'wallet': _rewards_wallet_payload(request.user),
        }, status=status.HTTP_201_CREATED)


class WithdrawalCancelView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        with transaction.atomic():
            try:
                row = WithdrawalRequest.objects.select_for_update().get(pk=pk, customer=request.user)
            except WithdrawalRequest.DoesNotExist:
                return Response({'error': 'Withdrawal request was not found.'}, status=status.HTTP_404_NOT_FOUND)
            if row.status != 'pending':
                return Response({'error': 'Only pending withdrawal requests can be cancelled.'}, status=status.HTTP_400_BAD_REQUEST)
            wallet, _ = RewardsWallet.objects.select_for_update().get_or_create(customer=request.user)
            wallet.available_taka += row.amount_taka
            wallet.save(update_fields=['available_taka', 'updated_at'])
            row.status = 'cancelled'
            row.processed_at = timezone.now()
            row.save(update_fields=['status', 'processed_at'])
        return Response({
            'message': 'Withdrawal request cancelled and the amount returned to your rewards wallet.',
            'withdrawal': _withdrawal_payload(row),
            'wallet': _rewards_wallet_payload(request.user),
        })
