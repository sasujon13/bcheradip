from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.utils import timezone

from childcare import auth_utils, models
from childcare.serializers import (
    ChildProfileSerializer,
    FriendCharacterSerializer,
    LessonItemSerializer,
    ModuleSerializer,
    ShortVideoSerializer,
)

# Canonical dashboard order matching Android APK titles/icons
DASHBOARD_MODULES = [
    ("friends", "Friends", "বন্ধু", "di_friends", 1),
    ("arabic", "Arabic", "আরবি", "di_arabic", 2),
    ("bengali", "Bengali", "বাংলা", "di_bengali", 3),
    ("english", "English", "ইংরেজি", "di_english", 4),
    ("math", "Math", "গণিত", "di_math", 5),
    ("iq", "IQ", "বুদ্ধিমত্তা", "di_iq", 6),
    ("animals", "Animals", "প্রাণী", "di_animals", 7),
    ("fruits", "Fruits", "ফলমূল", "di_fruits", 8),
    ("vegetables", "Vegetables", "সবজি", "di_vegetables", 9),
    ("human_body", "Human Body", "মানব দেহ", "di_hbody", 10),
    ("drawing_pad", "Drawing Pad", "খাতা", "di_khata", 11),
    ("quiz", "Quiz", "কুইজ", "di_quiz", 12),
    ("games", "Games", "খেলা", "di_games", 13),
    ("shorts", "Shorts", "শর্টস", "di_shorts", 14),
    ("contest", "Contest", "প্রতিযোগিতা", "di_contest", 15),
]


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "service": "childcare", "modules": 15})


class DashboardModulesView(APIView):
    """Return the 15 multi-functional dashboard modules for the Android app."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        qs = models.Module.objects.using("childcare").filter(is_enabled=True).order_by("sort_order")
        if not qs.exists():
            for key, en, bn, icon, order in DASHBOARD_MODULES:
                models.Module.objects.using("childcare").update_or_create(
                    key=key,
                    defaults={
                        "title_en": en,
                        "title_bn": bn,
                        "icon_name": icon,
                        "sort_order": order,
                        "is_enabled": True,
                    },
                )
            qs = models.Module.objects.using("childcare").filter(is_enabled=True).order_by("sort_order")
        return Response(ModuleSerializer(qs, many=True).data)


class LessonsByModuleView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, module_key):
        try:
            module = models.Module.objects.using("childcare").get(key=module_key)
        except models.Module.DoesNotExist:
            return Response({"detail": "Unknown module"}, status=status.HTTP_404_NOT_FOUND)
        section = request.query_params.get("section")
        qs = models.LessonItem.objects.using("childcare").filter(module=module, is_active=True)
        if section:
            qs = qs.filter(section=section)
        qs = qs.order_by("section", "sort_order", "id")
        return Response(
            {
                "module": ModuleSerializer(module).data,
                "lessons": LessonItemSerializer(qs, many=True).data,
            }
        )


class ShortsListView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        qs = models.ShortVideo.objects.using("childcare").filter(is_active=True).order_by("sort_order")
        return Response(ShortVideoSerializer(qs, many=True).data)


class FriendsListView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        qs = models.FriendCharacter.objects.using("childcare").filter(is_active=True).order_by("sort_order")
        return Response(FriendCharacterSerializer(qs, many=True).data)


class RegisterChildView(APIView):
    """
    Register parent (AILT-like: email + password) + child profile, then email OTP
    via the same Brevo SMTP credentials as AI Language Tutor.
    """

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = auth_utils.normalize_email(request.data.get("email", ""))
        password = str(request.data.get("password", "")).strip()
        username = str(request.data.get("username", "")).strip() or None
        parent_name = str(request.data.get("parent_name", "") or request.data.get("full_name", "")).strip()
        child_name = str(request.data.get("child_name", "") or request.data.get("full_name", "")).strip()
        mobile = str(request.data.get("mobile_number", "")).strip() or None
        day = request.data.get("day")
        month = request.data.get("month")
        year = request.data.get("year")
        address = str(request.data.get("address", "")).strip()
        device_id = str(request.data.get("deviceId", "") or request.data.get("device_id", "")).strip()

        if not email or "@" not in email:
            return Response({"detail": "Valid email is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not child_name or not day or not month or not year:
            return Response(
                {"detail": "child_name (or full_name), day, month, year are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        pwd_err = auth_utils.validate_password(password)
        if pwd_err:
            return Response({"detail": pwd_err}, status=status.HTTP_400_BAD_REQUEST)

        if models.ParentAccount.objects.using("childcare").filter(email=email).exists():
            return Response({"detail": "Email already registered"}, status=status.HTTP_409_CONFLICT)

        if not username:
            username = email.split("@", 1)[0][:64]
        base_username = username
        suffix = 1
        while models.ParentAccount.objects.using("childcare").filter(username=username).exists():
            username = f"{base_username[:50]}{suffix}"
            suffix += 1

        if mobile and models.ParentAccount.objects.using("childcare").filter(mobile_number=mobile).exists():
            return Response({"detail": "Mobile already registered"}, status=status.HTTP_409_CONFLICT)

        parent = models.ParentAccount.objects.using("childcare").create(
            email=email,
            username=username,
            password_hash=auth_utils.hash_password(password),
            full_name=parent_name or child_name,
            mobile_number=mobile,
            email_verified=False,
            is_verified=False,
            registered_device_id=device_id,
            role="user",
        )
        child = models.ChildProfile.objects.using("childcare").create(
            parent=parent,
            full_name=child_name,
            birth_day=int(day),
            birth_month=int(month),
            birth_year=int(year),
            address=address,
        )

        try:
            auth_utils.store_and_send_otp(email=email, channel=models.OtpCode.CHANNEL_REGISTER, purpose="Verification")
        except Exception as exc:
            return Response(
                {
                    "detail": str(exc),
                    "parent_id": parent.id,
                    "child": ChildProfileSerializer(child).data,
                    "next": "verify_otp",
                    "email": email,
                    "otpSent": False,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "ok": True,
                "parent_id": parent.id,
                "child": ChildProfileSerializer(child).data,
                "next": "verify_otp",
                "email": email,
                "otpSent": True,
                "message": "OTP sent to email",
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """Password login (AILT-style). Unverified accounts get a fresh OTP instead of a session."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        username = str(request.data.get("username", "") or request.data.get("email", "")).strip()
        password = str(request.data.get("password", "")).strip()
        device_id = str(request.data.get("deviceId", "") or request.data.get("device_id", "")).strip()

        if not username or not password:
            return Response({"detail": "username/email and password required"}, status=status.HTTP_400_BAD_REQUEST)

        parent = auth_utils.find_parent(username)
        if not parent:
            return Response({"detail": "NOT_REGISTERED", "code": "NOT_REGISTERED"}, status=status.HTTP_401_UNAUTHORIZED)
        if not auth_utils.verify_password(password, parent.password_hash):
            return Response(
                {"detail": "PASSWORD_MISMATCH", "code": "PASSWORD_MISMATCH"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not parent.email_verified:
            if not parent.email:
                return Response({"detail": "Account has no email for OTP"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                auth_utils.store_and_send_otp(
                    email=parent.email,
                    channel=models.OtpCode.CHANNEL_LOGIN,
                    purpose="Login",
                )
            except Exception as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
            return Response(
                {
                    "ok": True,
                    "requiresOtp": True,
                    "email": parent.email,
                    "message": "OTP sent to email",
                }
            )

        session = auth_utils.issue_session(parent, device_id)
        return Response(auth_utils.auth_payload(parent, session))


class SendOtpView(APIView):
    """Resend OTP to a registered email (register or login channel)."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = auth_utils.normalize_email(request.data.get("email", "") or request.data.get("target", ""))
        purpose = str(request.data.get("purpose", "Verification")).strip() or "Verification"
        channel = str(request.data.get("channel", "")).strip() or models.OtpCode.CHANNEL_EMAIL
        if channel not in {
            models.OtpCode.CHANNEL_EMAIL,
            models.OtpCode.CHANNEL_LOGIN,
            models.OtpCode.CHANNEL_REGISTER,
        }:
            channel = models.OtpCode.CHANNEL_EMAIL

        if not email or "@" not in email:
            return Response({"detail": "Email address required"}, status=status.HTTP_400_BAD_REQUEST)

        parent = models.ParentAccount.objects.using("childcare").filter(email=email).first()
        if not parent:
            return Response({"detail": "NOT_REGISTERED"}, status=status.HTTP_404_NOT_FOUND)

        try:
            auth_utils.store_and_send_otp(email=email, channel=channel, purpose=purpose)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"ok": True, "message": "OTP sent to email", "email": email})


class VerifyOtpView(APIView):
    """Verify email OTP and issue session token (AILT verify-email equivalent)."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        email = auth_utils.normalize_email(request.data.get("email", "") or request.data.get("target", ""))
        code = str(request.data.get("code", "") or request.data.get("otp", "")).strip()
        device_id = str(request.data.get("deviceId", "") or request.data.get("device_id", "")).strip()
        channel = str(request.data.get("channel", "")).strip()

        if not email or not code:
            return Response({"detail": "email and code required"}, status=status.HTTP_400_BAD_REQUEST)

        parent = models.ParentAccount.objects.using("childcare").filter(email=email).first()
        if not parent:
            return Response({"detail": "NOT_REGISTERED"}, status=status.HTTP_404_NOT_FOUND)

        channels = []
        if channel:
            channels = [channel]
        else:
            channels = [
                models.OtpCode.CHANNEL_REGISTER,
                models.OtpCode.CHANNEL_LOGIN,
                models.OtpCode.CHANNEL_EMAIL,
            ]

        ok = False
        for ch in channels:
            if auth_utils.verify_otp(email=email, channel=ch, code=code):
                ok = True
                break
        if not ok:
            return Response({"detail": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

        parent.email_verified = True
        parent.is_verified = True
        parent.save(using="childcare", update_fields=["email_verified", "is_verified", "updated_at"])
        session = auth_utils.issue_session(parent, device_id)
        return Response(auth_utils.auth_payload(parent, session))


class MeView(APIView):
    """Return profile for a valid session token."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        token = (
            request.headers.get("X-Session-Token")
            or request.query_params.get("sessionToken")
            or ""
        ).strip()
        if not token:
            auth = request.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                token = auth[7:].strip()
        if not token:
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        session = (
            models.DeviceSession.objects.using("childcare")
            .select_related("parent")
            .filter(token=token, is_active=True)
            .first()
        )
        if not session:
            return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
        if session.expires_at and session.expires_at < timezone.now():
            session.is_active = False
            session.save(using="childcare", update_fields=["is_active"])
            return Response({"detail": "Session expired"}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(auth_utils.auth_payload(session.parent, session))


def _session_from_request(request):
    token = (
        request.headers.get("X-Session-Token")
        or request.query_params.get("sessionToken")
        or (request.data.get("sessionToken") if hasattr(request, "data") else None)
        or ""
    )
    token = str(token or "").strip()
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        return None, Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    session = (
        models.DeviceSession.objects.using("childcare")
        .select_related("parent")
        .filter(token=token, is_active=True)
        .first()
    )
    if not session:
        return None, Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)
    if session.expires_at and session.expires_at < timezone.now():
        session.is_active = False
        session.save(using="childcare", update_fields=["is_active"])
        return None, Response({"detail": "Session expired"}, status=status.HTTP_401_UNAUTHORIZED)
    return session, None


class SyncScoresView(APIView):
    """Upsert learner scoreboard from the Android app (tutor E/B/A lanes)."""

    authentication_classes = []
    permission_classes = []

    def post(self, request):
        session, err = _session_from_request(request)
        if err:
            return err
        parent = session.parent
        child = auth_utils.primary_child(parent)
        total = int(request.data.get("totalPoints") or 0)
        modules = request.data.get("modules") or {}
        contest_week = str(request.data.get("contestWeek") or "")[:32]
        contest_score = int(request.data.get("contestScore") or 0)

        row, _created = models.LearnerScore.objects.using("childcare").update_or_create(
            parent=parent,
            defaults={
                "child": child,
                "total_points": max(0, total),
                "contest_week": contest_week,
                "contest_score": max(0, contest_score),
                "scores_json": modules if isinstance(modules, dict) else {},
            },
        )
        return Response(
            {
                "ok": True,
                "totalPoints": row.total_points,
                "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
            }
        )


class LeaderboardView(APIView):
    """Admin-only Top N among all synced learners."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        session, err = _session_from_request(request)
        if err:
            return err
        role = (session.parent.role or "user").lower()
        if role not in {"admin", "staff"}:
            return Response({"detail": "Admin only"}, status=status.HTTP_403_FORBIDDEN)

        try:
            top_n = int(request.query_params.get("top") or 10)
        except ValueError:
            top_n = 10
        top_n = max(1, min(top_n, 50))

        qs = (
            models.LearnerScore.objects.using("childcare")
            .select_related("parent", "child")
            .order_by("-total_points", "id")
        )
        count = qs.count()
        rows = []
        for i, row in enumerate(qs[:top_n]):
            child_name = ""
            if row.child_id and row.child:
                child_name = row.child.full_name
            elif row.parent:
                child_name = row.parent.full_name or row.parent.username or ""
            rows.append(
                {
                    "rank": i + 1,
                    "childName": child_name or "—",
                    "email": row.parent.email if row.parent else "",
                    "totalPoints": row.total_points,
                    "contestScore": row.contest_score,
                    "contestWeek": row.contest_week,
                }
            )
        return Response({"ok": True, "count": count, "top": rows})
