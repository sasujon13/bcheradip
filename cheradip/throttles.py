"""Rate limits for public authentication and account-recovery endpoints."""

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    scope = "auth_login"


class OtpRateThrottle(AnonRateThrottle):
    scope = "auth_otp"


class VerificationRateThrottle(AnonRateThrottle):
    scope = "auth_verify"


class PasswordCheckRateThrottle(UserRateThrottle):
    scope = "password_check"

