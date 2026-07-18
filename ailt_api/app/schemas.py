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


class AccountDeleteRequest(BaseModel):
    """Body for DELETE /auth/account — current password confirmation."""

    password: str = Field(min_length=1)


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


class ExtAdminPaddleConfigRequest(BaseModel):
    """Set Paddle credentials from the admin page. Blank/None = leave unchanged."""

    environment: str | None = Field(default=None, description="sandbox | production")
    apiKey: str | None = None
    webhookSecret: str | None = None
    clientToken: str | None = None
    pricePro: str | None = None
    pricePlus: str | None = None
    priceBusiness: str | None = None
    validate_: bool = Field(default=True, alias="validate")

    model_config = {"populate_by_name": True}


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
    # Line edits applied to files. Send a pre-summed ``lineEdits`` or the split
    # ``replacements`` + ``insertions`` (server sums them when lineEdits is 0).
    lineEdits: int = Field(0, ge=0)
    replacements: int = Field(0, ge=0)
    insertions: int = Field(0, ge=0)

    @property
    def total_lines(self) -> int:
        return self.lineEdits or (self.replacements + self.insertions)


class PaygEnableRequest(BaseModel):
    enabled: bool = True


class CreditTopupRequest(BaseModel):
    amountUsd: float = Field(..., ge=5.0, le=500.0, description="Prepaid credit amount in USD")


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


class ExtProjectKnowledgeUpsert(BaseModel):
    project_hash: str = Field(min_length=8, max_length=64)
    project_name: str = Field(default="", max_length=120)
    path_aliases: dict[str, str] = Field(default_factory=dict)
    summary: dict = Field(default_factory=dict)
    project_md_excerpt: str = Field(default="", max_length=12000)
    updated_at_ms: int = Field(ge=0)


class ExtProjectKnowledgeResponse(BaseModel):
    project_hash: str
    project_name: str = ""
    path_aliases: dict[str, str] = Field(default_factory=dict)
    summary: dict = Field(default_factory=dict)
    project_md_excerpt: str = ""
    updated_at_ms: int = 0


class ExtProjectKnowledgeListItem(BaseModel):
    project_hash: str
    project_name: str = ""
    updated_at_ms: int = 0
