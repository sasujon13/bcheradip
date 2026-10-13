"""
POST /api/trxid/ — ingest mobile-money style transaction JSON into ``cheradip_trxmanagement``.
"""
from decimal import Decimal, InvalidOperation
import secrets

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from django.db import IntegrityError, transaction

from .models import TrxManagement, TrxIdentity

_EXPECTED_KEYS = (
    "media",
    "received_amount",
    "currency",
    "sender_contact",
    "trxid",
    "transaction_date",
    "transaction_time",
    "confidence",
)


class TrxInboundAPIView(APIView):
    """
    Ingestion requires the independently configured payment intake secret.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        configured = str(getattr(settings, 'TRX_INGEST_SECRET', '') or '')
        supplied = str(request.headers.get('X-Cheradip-Ingest-Key', '') or '')
        if not configured or not secrets.compare_digest(configured, supplied):
            return Response({'detail': 'Payment intake authentication required.'}, status=status.HTTP_403_FORBIDDEN)
        data = request.data
        if not isinstance(data, dict):
            return Response(
                {"detail": "Body must be a JSON object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        missing = [k for k in _EXPECTED_KEYS if k not in data]
        if missing:
            return Response(
                {"detail": "Missing required keys.", "missing": missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        trxid_raw = data.get("trxid")
        if not str(trxid_raw).strip():
            return Response(
                {"detail": "trxid must be non-empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        trxid_norm = str(trxid_raw).strip()
        if len(trxid_norm) > 128:
            return Response({'detail': 'Transaction ID is too long.'}, status=status.HTTP_400_BAD_REQUEST)
        if TrxManagement.objects.filter(trxid=trxid_norm).exists():
            return Response(
                {"ok": True, "duplicate": True, "trxid": trxid_norm},
                status=status.HTTP_200_OK,
            )

        try:
            amount = Decimal(str(data["received_amount"]))
            conf = Decimal(str(data["confidence"]))
        except (InvalidOperation, TypeError, ValueError):
            return Response(
                {"detail": "received_amount and confidence must be numeric."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not amount.is_finite() or not Decimal('0') < amount <= Decimal('1000000'):
            return Response({'detail': 'received_amount must be a positive, finite amount.'}, status=400)
        if not conf.is_finite() or not Decimal('0') <= conf <= Decimal('1'):
            return Response({'detail': 'confidence must be between 0 and 1.'}, status=400)
        if str(data['currency']).strip().upper() != 'BDT':
            return Response({'detail': 'Only BDT payments are supported.'}, status=400)

        try:
            with transaction.atomic():
                row = TrxManagement.objects.create(
                    media=str(data["media"]).strip()[:64],
                    received_amount=amount,
                    currency='BDT',
                    sender_contact=str(data["sender_contact"]).strip()[:32],
                    trxid=trxid_norm,
                    transaction_date=str(data["transaction_date"]).strip()[:32],
                    transaction_time=str(data["transaction_time"]).strip()[:16],
                    confidence=conf,
                    verified=True,
                )
                TrxIdentity.objects.create(trxid=trxid_norm, transaction=row)
        except IntegrityError:
            return Response({'ok': True, 'duplicate': True, 'trxid': trxid_norm}, status=200)

        return Response(
            {
                "ok": True,
                "id": row.id,
                "trxid": row.trxid,
                "status": row.status,
                "token": row.token,
            },
            status=status.HTTP_201_CREATED,
        )

