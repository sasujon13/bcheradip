from django.contrib import admin

from . import models


@admin.register(models.ParentAccount)
class ParentAccountAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "username", "role", "email_verified", "mobile_number", "created_at")
    search_fields = ("email", "username", "mobile_number", "full_name")
    list_filter = ("role", "email_verified")
    list_editable = ("role",)

@admin.register(models.ChildProfile)
class ChildProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "parent", "birth_year", "updated_at")
    search_fields = ("full_name", "parent__email", "parent__mobile_number")


@admin.register(models.DeviceSession)
class DeviceSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "parent", "device_id", "is_active", "expires_at", "last_active_at")


@admin.register(models.OtpCode)
class OtpCodeAdmin(admin.ModelAdmin):
    list_display = ("id", "target", "channel", "code", "expires_at", "used")
    search_fields = ("target",)

@admin.register(models.Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("sort_order", "key", "title_en", "title_bn", "icon_name", "is_enabled")
    list_editable = ("is_enabled",)
    ordering = ("sort_order",)


@admin.register(models.LessonItem)
class LessonItemAdmin(admin.ModelAdmin):
    list_display = ("id", "module", "section", "label_en", "sort_order", "is_active")
    list_filter = ("module", "section", "is_active")


@admin.register(models.Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "module", "section", "is_active")


@admin.register(models.QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ("id", "quiz", "prompt", "correct_index", "sort_order")


@admin.register(models.Progress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ("id", "child", "module", "status", "score", "stars", "updated_at")


@admin.register(models.Drawing)
class DrawingAdmin(admin.ModelAdmin):
    list_display = ("id", "child", "title", "created_at")


@admin.register(models.GameScore)
class GameScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "child", "game_key", "score", "level", "played_at")


@admin.register(models.ShortVideo)
class ShortVideoAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "duration_sec", "sort_order", "is_active")


@admin.register(models.Contest)
class ContestAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "starts_at", "ends_at", "is_active")


@admin.register(models.ContestEntry)
class ContestEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "contest", "child", "score", "submitted_at")


@admin.register(models.FriendCharacter)
class FriendCharacterAdmin(admin.ModelAdmin):
    list_display = ("id", "name_en", "name_bn", "sort_order", "is_active")


@admin.register(models.LearnerScore)
class LearnerScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "parent", "child", "total_points", "contest_week", "contest_score", "updated_at")
    search_fields = ("parent__email", "child__full_name")
    ordering = ("-total_points",)
