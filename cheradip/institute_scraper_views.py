"""Staff-only controls for the public institute-directory updater."""

import requests
import re
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .institute_scraper import InstituteSourceError, process_institute_page
from .models import InstituteScrapePage, InstituteTeacher, Institutes
from .views import BearerTokenAuthentication


class InstituteScrapeAccessView(APIView):
    authentication_classes = [BearerTokenAuthentication, SessionAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response({'allowed': True, 'staff': True})


class InstituteScrapeStatusView(InstituteScrapeAccessView):
    def get(self, request):
        latest = InstituteScrapePage.objects.filter(source='banbeis').order_by('-processed_at').first()
        return Response({
            'localInstitutes': Institutes.objects.count(),
            'lastPage': latest.page if latest else None,
            'lastSize': latest.size if latest else None,
            'lastProcessedAt': latest.processed_at if latest else None,
            'sourceTotal': latest.source_total if latest else None,
            'banbeisUrl': 'https://institute-search.ieims.banbeis.gov.bd/',
            'emisUrl': 'https://emis.gov.bd/EMIS/portalone',
        })


class InstituteScrapePageView(InstituteScrapeAccessView):
    def post(self, request):
        try:
            page = int(request.data.get('page', 1))
            size = int(request.data.get('size', 10))
        except (TypeError, ValueError):
            return Response({'detail': 'Page and size must be whole numbers.'}, status=400)
        if not 1 <= page <= 100000 or not 1 <= size <= 25:
            return Response({'detail': 'Page must be positive and size must be 1–25.'}, status=400)
        mode = request.data.get('mode', 'preview')
        if mode not in {'preview', 'apply'}:
            return Response({'detail': 'Mode must be preview or apply.'}, status=400)
        enrich_emis = request.data.get('enrichEmis', True)
        if not isinstance(enrich_emis, bool):
            return Response({'detail': 'enrichEmis must be a boolean.'}, status=400)
        eiin = str(request.data.get('eiin') or '').strip() or None
        if eiin is not None and not re.fullmatch(r'\d{6}', eiin):
            return Response({'detail': 'EIIN must contain exactly six digits.'}, status=400)
        try:
            result = process_institute_page(
                page=page, size=size, enrich_emis=enrich_emis,
                apply=mode == 'apply', actor=request.user if mode == 'apply' else None, eiin=eiin,
            )
        except (requests.RequestException, InstituteSourceError) as exc:
            return Response({'detail': f'Institute source unavailable: {str(exc)[:180]}'}, status=502)
        return Response(result)


class InstituteTeacherDirectoryView(APIView):
    """Public roster labels; existing EIIN unlock controls personal contact fields."""
    authentication_classes = [BearerTokenAuthentication, SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, eiin):
        if not re.fullmatch(r'\d{6}', eiin):
            return Response({'detail': 'Invalid EIIN.'}, status=400)
        user = request.user
        settings = getattr(user, 'settings', None) if getattr(user, 'is_authenticated', False) else None
        paid = settings.get('unlocked_ntrca_eiins_v2', []) if isinstance(settings, dict) else []
        contacts_unlocked = bool(getattr(user, 'is_staff', False) or
                                 eiin in {str(value) for value in paid})
        rows = InstituteTeacher.objects.filter(eiin=eiin, listed=True).order_by('position', 'id')[:1000]
        teachers = [
            {'name': row.name, 'nameBn': row.name_bn, 'designation': row.designation,
             'subject': row.subject, 'mobile': row.mobile if contacts_unlocked else '',
             'email': row.email if contacts_unlocked else ''}
            for row in rows
        ]
        return Response({'eiin': eiin, 'contactsUnlocked': contacts_unlocked,
                         'count': len(teachers), 'teachers': teachers})
