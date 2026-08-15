"""
Child Care multi-functional learning app models.

ParentAccount mirrors AI Language Tutor `users` fields (email/username/password
+ verification) while ChildProfile keeps preschool child data.
"""

from django.db import models
from django.utils import timezone


class ParentAccount(models.Model):
    """Account table aligned with ailanguagetutor.users (email OTP auth)."""

    email = models.CharField(max_length=255, unique=True, null=True, blank=True, db_index=True)
    username = models.CharField(max_length=64, unique=True, null=True, blank=True, db_index=True)
    password_hash = models.CharField(max_length=255, blank=True, default="")
    full_name = models.CharField(max_length=120, blank=True, default="")
    mobile_number = models.CharField(max_length=20, unique=True, null=True, blank=True, db_index=True)
    role = models.CharField(max_length=16, default="user")
    email_verified = models.BooleanField(default=False)
    registered_device_id = models.CharField(max_length=128, blank=True, default="")
    # Legacy flag — prefer email_verified for OTP flow
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cc_parents"
        verbose_name = "Parent account"
        verbose_name_plural = "Parent accounts"

    def __str__(self):
        return self.email or self.username or self.mobile_number or f"parent-{self.pk}"


class ChildProfile(models.Model):
    parent = models.ForeignKey(ParentAccount, on_delete=models.CASCADE, related_name="children")
    full_name = models.CharField(max_length=120)
    birth_day = models.PositiveSmallIntegerField()
    birth_month = models.PositiveSmallIntegerField()
    birth_year = models.PositiveSmallIntegerField()
    address = models.CharField(max_length=255, blank=True, default="")
    avatar_url = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cc_children"
        verbose_name = "Child profile"
        verbose_name_plural = "Child profiles"

    def __str__(self):
        return self.full_name


class DeviceSession(models.Model):
    parent = models.ForeignKey(ParentAccount, on_delete=models.CASCADE, related_name="sessions")
    token = models.CharField(max_length=128, unique=True, null=True, blank=True, db_index=True)
    device_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    device_label = models.CharField(max_length=120, blank=True, default="")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_active_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cc_device_sessions"
        verbose_name = "Device session"
        verbose_name_plural = "Device sessions"


class OtpCode(models.Model):
    """Matches ailanguagetutor.otp_codes shape (target + channel + used)."""

    CHANNEL_EMAIL = "email"
    CHANNEL_LOGIN = "login"
    CHANNEL_REGISTER = "register"

    target = models.CharField(max_length=255, db_index=True)
    channel = models.CharField(max_length=32, default=CHANNEL_EMAIL)
    code = models.CharField(max_length=8)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cc_otp_codes"
        verbose_name = "OTP code"
        verbose_name_plural = "OTP codes"


class Module(models.Model):
    """One row per dashboard tile (1–15)."""

    key = models.SlugField(max_length=40, unique=True)
    title_en = models.CharField(max_length=80)
    title_bn = models.CharField(max_length=80, blank=True, default="")
    icon_name = models.CharField(max_length=80, help_text="Android drawable name, e.g. di_friends")
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "cc_modules"
        ordering = ["sort_order", "id"]
        verbose_name = "Dashboard module"
        verbose_name_plural = "Dashboard modules"

    def __str__(self):
        return f"{self.sort_order}. {self.title_en}"


class LessonItem(models.Model):
    """Generic learnable card used by English/Arabic/Bengali/Animals/Fruits/etc."""

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    section = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="e.g. capital, small, numbers, signs, alphabet, body_parts",
    )
    label_en = models.CharField(max_length=120)
    label_bn = models.CharField(max_length=120, blank=True, default="")
    image_ref = models.CharField(max_length=200, blank=True, default="", help_text="drawable or URL")
    audio_ref = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    meta_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "cc_lesson_items"
        ordering = ["module_id", "section", "sort_order", "id"]
        verbose_name = "Lesson item"
        verbose_name_plural = "Lesson items"


class Quiz(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="quizzes")
    title = models.CharField(max_length=160)
    section = models.CharField(max_length=40, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "cc_quizzes"
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"

    def __str__(self):
        return self.title


class QuizQuestion(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    prompt = models.TextField()
    prompt_audio_ref = models.CharField(max_length=200, blank=True, default="")
    prompt_image_ref = models.CharField(max_length=200, blank=True, default="")
    choices_json = models.JSONField(default=list, help_text='["A","B","C","D"]')
    correct_index = models.PositiveSmallIntegerField(default=0)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "cc_quiz_questions"
        ordering = ["quiz_id", "sort_order", "id"]
        verbose_name = "Quiz question"
        verbose_name_plural = "Quiz questions"


class Progress(models.Model):
    child = models.ForeignKey(ChildProfile, on_delete=models.CASCADE, related_name="progress")
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="progress")
    lesson_item = models.ForeignKey(
        LessonItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="progress"
    )
    status = models.CharField(max_length=32, default="started")  # started|completed
    score = models.IntegerField(default=0)
    stars = models.PositiveSmallIntegerField(default=0)
    extra_json = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cc_progress"
        verbose_name = "Progress"
        verbose_name_plural = "Progress"


class Drawing(models.Model):
    """Drawing Pad (Khata) saves."""

    child = models.ForeignKey(ChildProfile, on_delete=models.CASCADE, related_name="drawings")
    title = models.CharField(max_length=120, blank=True, default="")
    file_path = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cc_drawings"
        verbose_name = "Drawing"
        verbose_name_plural = "Drawings"


class GameScore(models.Model):
    child = models.ForeignKey(ChildProfile, on_delete=models.CASCADE, related_name="game_scores")
    game_key = models.SlugField(max_length=40)
    score = models.IntegerField(default=0)
    level = models.PositiveIntegerField(default=1)
    played_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cc_game_scores"
        verbose_name = "Game score"
        verbose_name_plural = "Game scores"


class ShortVideo(models.Model):
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    media_url = models.CharField(max_length=500)
    duration_sec = models.PositiveIntegerField(default=0)
    age_tag = models.CharField(max_length=40, blank=True, default="2-6")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "cc_short_videos"
        ordering = ["sort_order", "id"]
        verbose_name = "Short video"
        verbose_name_plural = "Short videos"


class Contest(models.Model):
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    module = models.ForeignKey(Module, on_delete=models.SET_NULL, null=True, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "cc_contests"
        verbose_name = "Contest"
        verbose_name_plural = "Contests"


class ContestEntry(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name="entries")
    child = models.ForeignKey(ChildProfile, on_delete=models.CASCADE, related_name="contest_entries")
    score = models.IntegerField(default=0)
    media_path = models.CharField(max_length=500, blank=True, default="")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cc_contest_entries"
        verbose_name = "Contest entry"
        verbose_name_plural = "Contest entries"


class FriendCharacter(models.Model):
    """Friends module — offline companion characters (MVP)."""

    name_en = models.CharField(max_length=80)
    name_bn = models.CharField(max_length=80, blank=True, default="")
    image_ref = models.CharField(max_length=200, blank=True, default="")
    greeting_audio_ref = models.CharField(max_length=200, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "cc_friend_characters"
        ordering = ["sort_order", "id"]
        verbose_name = "Friend character"
        verbose_name_plural = "Friend characters"


class LearnerScore(models.Model):
    """Synced tutor scoreboard: total points + per-module E/B/A lanes."""

    parent = models.OneToOneField(
        ParentAccount, on_delete=models.CASCADE, related_name="learner_score"
    )
    child = models.ForeignKey(
        ChildProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learner_scores",
    )
    total_points = models.IntegerField(default=0, db_index=True)
    contest_week = models.CharField(max_length=32, blank=True, default="")
    contest_score = models.IntegerField(default=0)
    scores_json = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cc_learner_scores"
        verbose_name = "Learner score"
        verbose_name_plural = "Learner scores"
        ordering = ["-total_points", "id"]

    def __str__(self):
        return f"{self.parent_id}: {self.total_points} pts"
