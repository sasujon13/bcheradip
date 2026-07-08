from pydantic import AliasChoices, BaseModel, Field


class AuthLoginRequest(BaseModel):
    username: str
    password: str
    deviceId: str | None = None


class AuthLoginResponse(BaseModel):
    email: str
    role: str = "user"
    whatsapp: str | None = None
    sessionToken: str | None = None
    emailVerified: bool | None = None
    whatsappVerified: bool | None = None


class OtpRequest(BaseModel):
    target: str


class OtpVerifyRequest(BaseModel):
    target: str
    code: str


class SignupInitRequest(BaseModel):
    fullName: str = Field(min_length=2, max_length=80)
    email: str
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    deviceId: str | None = None


class SignupInitResponse(BaseModel):
    ok: bool = True
    message: str = "Account created"
    email: str = ""
    role: str = "user"
    sessionToken: str | None = None


class RecoverySendRequest(BaseModel):
    username: str
    deviceId: str | None = None


class RecoverySendResponse(BaseModel):
    ok: bool = True
    message: str = ""
    requiresOtp: bool = True


class RecoveryResetRequest(BaseModel):
    username: str
    newPassword: str = Field(min_length=8)
    otp: str | None = None
    deviceId: str | None = None


class PasswordUpdateSendRequest(BaseModel):
    currentPassword: str
    deviceId: str | None = None


class PasswordUpdateSendResponse(BaseModel):
    ok: bool = True
    message: str = ""
    requiresOtp: bool = True


class PasswordUpdateConfirmRequest(BaseModel):
    newPassword: str = Field(min_length=8)
    currentPassword: str
    otp: str | None = None
    deviceId: str | None = None


class EmailChangeSendRequest(BaseModel):
    deviceId: str | None = None


class EmailChangeSendResponse(BaseModel):
    ok: bool = True
    message: str = ""
    requiresOtp: bool = True


class EmailChangeConfirmRequest(BaseModel):
    newEmail: str
    otp: str | None = None
    deviceId: str | None = None


class ReferralWithdrawRequest(BaseModel):
    method: str = Field(description="paypal, bank_transfer, or mobile_wallet")
    payoutDetails: str = Field(min_length=3)
    amountUsd: float | None = None


class ReferralWithdrawResponse(BaseModel):
    ok: bool
    message: str
    balanceUsd: float
    withdrawalId: int | None = None


class DeviceRegisterRequest(BaseModel):
    deviceId: str
    model: str
    osVersion: str


class DeviceRegisterResponse(BaseModel):
    trialEndsAt: int | None = None
    trialDaysRemaining: int = 30


class GuestAiSyncRequest(BaseModel):
    deviceId: str
    localCount: int = Field(ge=0)


class GuestAiRecordRequest(BaseModel):
    deviceId: str


class GuestAiUsageResponse(BaseModel):
    count: int = 0
    limit: int = 99
    requiresLogin: bool = False


class BillingVerifyRequest(BaseModel):
    purchaseToken: str
    productId: str
    slot1Code: str | None = None
    slot2Code: str | None = None
    referralBalanceUsd: float | None = Field(None, ge=0)


class ReferralGiftRequest(BaseModel):
    recipientEmail: str = Field(min_length=3)
    amountUsd: float = Field(gt=0)


class BillingVerifyResponse(BaseModel):
    active: bool
    expiresAt: int | None = None
    tier: str | None = None


class ExtSignupRequest(BaseModel):
    email: str
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)
    fullName: str | None = Field(default=None, max_length=80)
    deviceId: str | None = None


class ExtLoginRequest(BaseModel):
    username: str
    password: str
    deviceId: str | None = None


class ExtAuthResponse(BaseModel):
    id: int
    email: str | None = None
    username: str | None = None
    fullName: str | None = None
    role: str = "user"
    sessionToken: str | None = None


class ExtPasswordChangeRequest(BaseModel):
    currentPassword: str
    newPassword: str = Field(min_length=8)
    deviceId: str | None = None


class ExtRecoverySendRequest(BaseModel):
    email: str


class ExtRecoveryResetRequest(BaseModel):
    email: str
    otp: str
    newPassword: str = Field(min_length=8)


class ExtAdminCreditGrantRequest(BaseModel):
    teamId: int
    amountUsd: float = Field(description="Positive to grant, negative to deduct")
    reason: str = Field(default="admin_grant", max_length=64)


class ExtAdminUserUpdateRequest(BaseModel):
    role: str | None = Field(default=None, description="user | admin")
    active: bool | None = None


class ExtAdminPlanUpdateRequest(BaseModel):
    plan: str = Field(description="free | pro | plus | business")
    paygEnabled: bool | None = None
    status: str | None = Field(default=None, description="active | past_due | canceled")


class SubscriptionCheckoutRequest(BaseModel):
    plan: str = Field(description="pro | plus | business")
    seats: int = Field(1, ge=1, le=1000)
    enablePayg: bool = False


class SubscriptionCheckoutResponse(BaseModel):
    ok: bool = True
    checkoutUrl: str | None = None
    pricingUrl: str | None = None
    billingEnabled: bool = False
    provider: str = "paddle"
    stripeEnabled: bool = False  # back-compat alias for older extension clients
    message: str = ""


class LicenseVerifyRequest(BaseModel):
    licenseKey: str = Field(min_length=6)


class UsageRecordRequest(BaseModel):
    requests: int = Field(1, ge=0)
    tokens: int = Field(0, ge=0)


class PaygEnableRequest(BaseModel):
    enabled: bool = True


class PromoValidateRequest(BaseModel):
    code: str
    base_price: float = Field(2.0, alias="base_price")
    slot1_code: str | None = Field(None, alias="slot1_code")

    model_config = {"populate_by_name": True}


class AdminPromoCodeDto(BaseModel):
    code: str
    discount_percent: int = Field(
        validation_alias=AliasChoices("discount_percent", "discountPercent"),
    )
    active: bool = True
    auto_apply: bool = Field(
        default=False,
        validation_alias=AliasChoices("auto_apply", "autoApply"),
    )
    paywall_slot: int = Field(
        default=2,
        validation_alias=AliasChoices("paywall_slot", "paywallSlot"),
    )

    model_config = {"populate_by_name": True}


class AdminPromoPatchDto(BaseModel):
    discount_percent: int | None = Field(
        None,
        validation_alias=AliasChoices("discount_percent", "discountPercent"),
    )
    active: bool | None = None
    auto_apply: bool | None = Field(
        None,
        validation_alias=AliasChoices("auto_apply", "autoApply"),
    )
    paywall_slot: int | None = Field(
        None,
        validation_alias=AliasChoices("paywall_slot", "paywallSlot"),
    )

    model_config = {"populate_by_name": True}


class ReferralPolicyPatchDto(BaseModel):
    active: bool | None = None
    buyer_discount_percent: int | None = Field(None, alias="buyer_discount_percent")
    commission_percent: int | None = Field(None, alias="commission_percent")
    notice_text: str | None = Field(None, alias="notice_text")

    model_config = {"populate_by_name": True}


class AiActivityMetadataRequest(BaseModel):
    text: str
    language_code: str


class AiParagraphRequest(BaseModel):
    paragraph: str
    source_lang: str
    target_lang: str


class AiRoutingPolicyUpdateRequest(BaseModel):
    mode: str
    prefer_paid_when_free_exhausted: bool | None = None


class AiProviderToggleRequest(BaseModel):
    enabled: bool


class LearningActivityDto(BaseModel):
    client_id: str
    title: str
    summary: str | None = None
    activity_type: str
    language_code: str
    output_language_code: str | None = None
    input_text: str | None = None
    output_text: str | None = None
    tags_json: str | None = None
    is_saved: bool = False
    created_at_ms: int
    updated_at_ms: int


class LearningActivitySyncRequest(BaseModel):
    activities: list[LearningActivityDto] = Field(default_factory=list)


class LearningActivitySyncResponse(BaseModel):
    activities: list[LearningActivityDto] = Field(default_factory=list)
    server_time_ms: int
