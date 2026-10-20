from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import LiveClass
from .views import BearerTokenAuthentication


class LiveClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = LiveClass
        fields = ('id', 'title', 'subject', 'level', 'topic', 'teacher_name', 'description',
                  'starts_at', 'ends_at', 'join_url', 'status')


class LiveClassScheduleView(APIView):
    authentication_classes = [BearerTokenAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            limit = max(1, min(100, int(request.query_params.get('limit', 100))))
        except (ValueError, TypeError):
            return Response({'detail': 'Use a whole-number limit.'}, status=400)
        now = timezone.now()
        classes = LiveClass.objects.filter(is_published=True, status__in=['scheduled', 'live'], ends_at__gt=now).exclude(join_url='')
        next_class = classes.filter(starts_at__gte=now).first() or classes.first()
        return Response({
            'classes': LiveClassSerializer(classes[:limit], many=True).data,
            'nextClass': LiveClassSerializer(next_class).data if next_class else None,
            'timezone': 'Asia/Dhaka',
        })
