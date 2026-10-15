"""Staff-only controls for the public institute-directory updater."""

from datetime import date
import requests
import re
from django.http import FileResponse
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .institute_scraper import InstituteSourceError, process_institute_page
from .institute_refresh import PublicRefreshBusy, enqueue_public_refresh, refresh_summary
from .institute_update_runs import (
    InstituteUpdateBusy, failed_eiins_from_file, log_path, process_step,
    rebuild_logs_locked, run_summary, start_or_resume_run,
)
from .models import (
    Banbeis, InstituteRefreshRequest, InstituteScrapePage, InstituteSourceSnapshot,
    InstituteTeacher, InstituteUpdateRun, Institutes,
    Vacancy5, Vacancy6, Vacancy7, Recommend5, Recommend6, Recommend7,
)
from .serializers import BanbeisSerializer
from .views import BearerTokenAuthentication
from .unlock_entitlements import effective_institute_eiins


PUBLIC_BANBEIS_DETAILS = (
    'establishmentDate', 'stopLegacy', 'stopDate', 'telephone', 'instituteHasEnglishVersion',
    'unionNameBn', 'cityCorporationNameBn', 'areaStatusNameBn', 'educationLevelNameBn',
    'geographicalPositionNameBn', 'instituteForWhomNameBn', 'managementNameBn',
    'address', 'webSite', 'constituencyNameBn', 'constituencyCode',
    'postOfficeNameBn', 'postOfficeCode', 'wardNo', 'mouzaNameBn',
)

_BANBEIS_ALREADY_DISPLAYED = frozenset(PUBLIC_BANBEIS_DETAILS) | {
    'eiinNo', 'instituteName', 'instituteNameBn', 'instituteTypeNameBn',
    'divisionNameBn', 'districtNameBn', 'thanaNameBn', 'mobile',
    'mobileAlternate', 'email',
}
_PUBLIC_EXTRA_SUFFIXES = ('Name', 'NameBn', 'Count', 'Total', 'Date', 'Status', 'Level')
_PRIVATE_FIELD_PARTS = ('password', 'secret', 'token', 'key', 'personal', 'nationalid',
                        'birth', 'salary', 'bank', 'payment', 'nid', 'passport')


def _additional_public_banbeis_fields(source):
    """Show new, simple institute-level source fields without exposing raw snapshots."""
    details = []
    for key, value in source.items():
        if key in _BANBEIS_ALREADY_DISPLAYED or not re.fullmatch(r'[A-Za-z][A-Za-z0-9]*', key):
            continue
        folded = key.casefold()
        if (folded in {'id', 'esurveyid'} or folded.endswith(('id', 'code')) or
                any(private in folded for private in _PRIVATE_FIELD_PARTS) or
                not key.endswith(_PUBLIC_EXTRA_SUFFIXES)):
            continue
        if not isinstance(value, (str, int, float, bool)) or value in ('', None):
            continue
        label = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', key).replace(' Bn', ' (Bangla)')
        label = label[0].upper() + label[1:]
        details.append({'label': label, 'value': str(value)[:300]})
        if len(details) >= 30:
            break
    return details


def _staff_sort_key(row):
    designation = (row.designation or '').strip()
    label = designation.casefold()
    if any(word in label for word in ('উপাধ্যক্ষ', 'সহকারী প্রধান', 'vice principal', 'assistant head')):
        rank = 1
    elif any(word in label for word in ('অধ্যক্ষ', 'প্রধান শিক্ষক', 'প্রধানশিক্ষক', 'principal', 'headmaster')):
        rank = 0
    elif any(word in label for word in ('প্রভাষক', 'শিক্ষক', 'lecturer', 'teacher', 'ইন্সট্রাক্টর', 'instructor')):
        rank = 2
    else:
        rank = 3
    return (rank, label, row.joining_date or row.present_joining_date or date.max,
            (row.name_bn or row.name).casefold(), row.position)


class PublicInstitutePageDetailsView(APIView):
    """Full institute-page details without changing paid access on other pages."""
    authentication_classes = [BearerTokenAuthentication, SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, eiin):
        if not re.fullmatch(r'\d{6}', eiin):
            return Response({'detail': 'Invalid EIIN.'}, status=400)
        row = Banbeis.objects.filter(EIIN=int(eiin)).first()
        banbeis = BanbeisSerializer(row, context={'request': request, 'public_detail': True}).data if row else None
        snapshot = InstituteSourceSnapshot.objects.filter(eiin=eiin).first()
        source = snapshot.banbeis if snapshot and isinstance(snapshot.banbeis, dict) else {}
        source_details = {key: source[key] for key in PUBLIC_BANBEIS_DETAILS if key in source}
        teacher_rows = InstituteTeacher.objects.filter(eiin=eiin, listed=True).order_by('position', 'id')[:1000]
        teachers = [
            {'name': teacher.name, 'nameBn': teacher.name_bn,
             'designation': teacher.designation, 'subject': teacher.subject,
             'mobile': teacher.mobile, 'email': teacher.email,
             'pdsId': teacher.pds_id, 'indexNo': teacher.index_no,
             'district': teacher.district_name, 'bcsBatch': teacher.bcs_batch,
             'photoUrl': teacher.photo_url,
             'joiningDate': teacher.joining_date.isoformat() if teacher.joining_date else None,
             'presentJoiningDate': teacher.present_joining_date.isoformat() if teacher.present_joining_date else None}
            for teacher in sorted(teacher_rows, key=_staff_sort_key)
        ]
        return Response({'banbeis': banbeis, 'sourceDetails': source_details,
                         'additionalDetails': _additional_public_banbeis_fields(source),
                         'sourceUpdatedAt': snapshot.last_banbeis_sync_at if snapshot else None,
                         'staffUpdatedAt': snapshot.last_emis_sync_at if snapshot else None,
                         'teachers': teachers, 'contactsUnlocked': True})


class PublicInstituteRefreshView(APIView):
    """Visitors can queue a single bounded update; only the worker contacts sources."""
    authentication_classes = [BearerTokenAuthentication, SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, eiin):
        if not re.fullmatch(r'\d{6}', eiin):
            return Response({'detail': 'Invalid EIIN.'}, status=400)
        return Response(refresh_summary(InstituteRefreshRequest.objects.filter(eiin=eiin).first()))

    def post(self, request, eiin):
        try:
            summary = enqueue_public_refresh(eiin)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        except LookupError as exc:
            return Response({'detail': str(exc)}, status=404)
        except PublicRefreshBusy as exc:
            return Response({'detail': str(exc)}, status=429)
        return Response(summary, status=202 if summary['status'] in {'queued', 'running'} else 200)


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
    """Legacy EIIN-scoped staff roster; vacancy-page contact unlock still applies."""
    authentication_classes = [BearerTokenAuthentication, SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, eiin):
        if not re.fullmatch(r'\d{6}', eiin):
            return Response({'detail': 'Invalid EIIN.'}, status=400)
        user = request.user
        contacts_unlocked = bool(getattr(user, 'is_staff', False) or
                                 eiin in effective_institute_eiins(user, request))
        rows = InstituteTeacher.objects.filter(eiin=eiin, listed=True).order_by('position', 'id')[:1000]
        teachers = [
            {'name': row.name, 'nameBn': row.name_bn, 'designation': row.designation,
             'subject': row.subject, 'mobile': row.mobile if contacts_unlocked else '',
             'email': row.email if contacts_unlocked else ''}
            for row in rows
        ]
        return Response({'eiin': eiin, 'contactsUnlocked': contacts_unlocked,
                         'count': len(teachers), 'teachers': teachers})


class InstituteNtrcaRecordsView(APIView):
    """Public, EIIN-scoped vacancy and recommendation records already in the job database."""
    authentication_classes = [BearerTokenAuthentication, SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request, eiin):
        if not re.fullmatch(r'\d{6}', eiin):
            return Response({'detail': 'Invalid EIIN.'}, status=400)
        number = int(eiin)
        vacancies = []
        recommendations = []
        for cycle, model in ((5, Vacancy5), (6, Vacancy6), (7, Vacancy7)):
            rows = model.objects.filter(EIIN=number).order_by('VPID').values(
                'VPID', 'Name', 'District', 'Thana', 'Designation',
                'Subject', 'Vacancy', 'Type', 'Status',
            )
            vacancies.extend({'cycle': cycle, **row} for row in rows)
        for cycle, model in ((5, Recommend5), (6, Recommend6), (7, Recommend7)):
            rows = model.objects.filter(EIIN=number).order_by('id').values(
                'id', 'District', 'Thana', 'Designation', 'Post', 'Merit',
                'Roll', 'Name', 'Code', 'Mark', 'Rank', 'Serial', 'Subject',
            )
            recommendations.extend({'cycle': cycle, **row} for row in rows)
        return Response({'eiin': eiin, 'vacancies': vacancies, 'recommendations': recommendations})


class InstituteAutomaticStatusView(InstituteScrapeAccessView):
    def get(self, request):
        return Response({'run': run_summary(InstituteUpdateRun.objects.first())})


class InstituteAutomaticStartView(InstituteScrapeAccessView):
    def post(self, request):
        mode = request.data.get('mode', 'all')
        if mode not in {'all', 'failed'}:
            return Response({'detail': 'Mode must be all or failed.'}, status=400)
        try:
            run = start_or_resume_run() if mode == 'all' else InstituteUpdateRun.objects.first()
        except InstituteUpdateBusy as exc:
            return Response({'detail': str(exc)}, status=409)
        if run is None:
            return Response({'detail': 'Run Update first to create a failed-EIIN file.'}, status=400)
        if mode == 'failed':
            try:
                rebuild_logs_locked(run)
            except InstituteUpdateBusy as exc:
                return Response({'detail': str(exc)}, status=409)
            count = len(failed_eiins_from_file(run))
            if not count:
                return Response({'detail': 'The failed-EIIN file has no remaining failures.'}, status=400)
        else:
            count = run.total
        return Response({'run': run_summary(run), 'mode': mode, 'selected': count})


class InstituteAutomaticStepView(InstituteScrapeAccessView):
    def post(self, request):
        mode = request.data.get('mode', 'all')
        run = InstituteUpdateRun.objects.first()
        if run is None or str(run.pk) != str(request.data.get('runId') or ''):
            return Response({'detail': 'This update run is no longer current. Refresh its status.'}, status=409)
        try:
            result = process_step(run, mode=mode, actor=request.user,
                                  after=str(request.data.get('after') or ''))
        except InstituteUpdateBusy as exc:
            return Response({'detail': str(exc)}, status=409)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response(result)


class InstituteAutomaticLogView(InstituteScrapeAccessView):
    def get(self, request, kind):
        if kind not in {'completed', 'failed'}:
            return Response({'detail': 'Unknown log type.'}, status=404)
        run = InstituteUpdateRun.objects.first()
        if run is None:
            return Response({'detail': 'No institute update has started.'}, status=404)
        path = log_path(run, kind)
        try:
            rebuild_logs_locked(run)  # Include any completed EIINs from an interrupted batch.
        except InstituteUpdateBusy as exc:
            return Response({'detail': str(exc)}, status=409)
        return FileResponse(path.open('rb'), as_attachment=True, filename=path.name,
                            content_type='text/plain; charset=utf-8')
