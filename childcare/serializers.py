from rest_framework import serializers

from childcare import models


class ModuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Module
        fields = (
            "id",
            "key",
            "title_en",
            "title_bn",
            "icon_name",
            "sort_order",
            "is_enabled",
            "description",
        )


class LessonItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.LessonItem
        fields = (
            "id",
            "module",
            "section",
            "label_en",
            "label_bn",
            "image_ref",
            "audio_ref",
            "sort_order",
            "meta_json",
            "is_active",
        )


class ChildProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ChildProfile
        fields = (
            "id",
            "full_name",
            "birth_day",
            "birth_month",
            "birth_year",
            "address",
            "avatar_url",
        )


class ShortVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ShortVideo
        fields = (
            "id",
            "title",
            "description",
            "media_url",
            "duration_sec",
            "age_tag",
            "sort_order",
        )


class FriendCharacterSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.FriendCharacter
        fields = (
            "id",
            "name_en",
            "name_bn",
            "image_ref",
            "greeting_audio_ref",
            "sort_order",
        )
