"""
POST /api/trxid/ — ingest mobile-money style transaction JSON into ``cheradip_trxmanagement``.
"""
from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TrxManagement

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
    Public webhook-style endpoint (no auth). Duplicate ``trxid`` returns 200 without inserting again.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
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

        row = TrxManagement.objects.create(
            media=str(data["media"]).strip()[:64],
            received_amount=amount,
            currency=str(data["currency"]).strip()[:16],
            sender_contact=str(data["sender_contact"]).strip()[:32],
            trxid=trxid_norm[:128],
            transaction_date=str(data["transaction_date"]).strip()[:32],
            transaction_time=str(data["transaction_time"]).strip()[:16],
            confidence=conf,
        )

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

