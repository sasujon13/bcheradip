"""Authenticated student-dashboard progress APIs.

The exam-set player used to keep results only in browser localStorage while the
dashboard called several legacy endpoints that no longer existed.  These views
store a compact result history inside ``Customer.settings`` so progress follows
the signed-in student without introducing a second exam database.
"""

from collections import defaultdict
from datetime import date, timedelta
from io import BytesIO

from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer
from .views import (
    BearerTokenAuthentication,
    REPORTLAB_AVAILABLE,
    _get_pdf_bengali_font,
)


RESULTS_KEY = 'student_exam_results'
ACTIVITY_KEY = 'student_activity_dates'
MAX_RESULTS = 250


def _settings(value):
    return value if isinstance(value, dict) else {}


def _results(customer):
    value = _settings(customer.settings).get(RESULTS_KEY, [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _completed_results(customer):
    """Return submitted/timed-out exams; old records predate this flag and count as complete."""
    return [item for item in _results(customer) if item.get('completed', True) is not False]


def _number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _result_time(item):
    value = parse_datetime(str(item.get('at') or ''))
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value


def _period_start(period):
    days = {
        'weekly': 7,
        'monthly': 30,
        'quarterly': 90,
        'half-yearly': 183,
        'yearly': 365,
    }.get(period)
    return timezone.now() - timedelta(days=days) if days else None


def _filtered_results(customer, period='all-time', level='', subject=''):
    start = _period_start(period)
    output = []
    for item in _completed_results(customer):
        if start:
            attempted_at = _result_time(item)
            if attempted_at is None or attempted_at < start:
                continue
        if level and str(item.get('levelTr') or '') != level:
            continue
        if subject and str(item.get('subjectTr') or '') != subject:
            continue
        output.append(item)
    return output


def _activity(customer):
    today = timezone.localdate().isoformat()
    dates = _settings(customer.settings).get(ACTIVITY_KEY, [])
    dates = [str(value) for value in dates if value] if isinstance(dates, list) else []
    if today not in dates:
        dates.append(today)
    return sorted(set(dates))[-400:]


def _streaks(date_values):
    parsed = []
    for value in date_values:
        try:
            parsed.append(date.fromisoformat(value))
        except (TypeError, ValueError):
            continue
    days = sorted(set(parsed))
    if not days:
        return 0, 0
    longest = run = 1
    for previous, current in zip(days, days[1:]):
        run = run + 1 if current == previous + timedelta(days=1) else 1
        longest = max(longest, run)
    today = timezone.localdate()
    current = 0
    cursor = today if today in days else today - timedelta(days=1)
    day_set = set(days)
    while cursor in day_set:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def _summary(customer, *, touch=False):
    if touch:
        with transaction.atomic():
            locked = Customer.objects.select_for_update().get(pk=customer.pk)
            data = _settings(locked.settings).copy()
            data[ACTIVITY_KEY] = _activity(locked)
            locked.settings = data
            locked.save(update_fields=['settings'])
            customer.settings = data

    results = _completed_results(customer)
    completed = len(results)
    correct = sum(max(0, _integer(item.get('correct'))) for item in results)
    answered = sum(max(0, _integer(item.get('total'))) for item in results)
    average = round(sum(_number(item.get('score')) for item in results) / completed) if completed else 0
    accuracy = round(correct * 100 / answered) if answered else 0
    points = correct * 10
    level_size = 500
    activity = _settings(customer.settings).get(ACTIVITY_KEY, [])
    streak, longest = _streaks(activity if isinstance(activity, list) else [])
    return {
        'examsCompleted': completed,
        'averageScore': average,
        'currentRank': 0,
        'loginStreak': streak,
        'streak': streak,
        'longestStreak': longest,
        'totalPoints': points,
        'currentLevel': points // level_size + 1,
        'xp': points % level_size,
        'xpToNextLevel': level_size,
        'questionsAnswered': answered,
        'correctAnswers': correct,
        'accuracy': accuracy,
    }


def _ranked_customers(period='all-time', level='', subject='', group=''):
    group_aliases = {
        'S': 'Science', 'A': 'Humanities', 'B': 'Business Studies',
        'I': 'Islamic Studies', 'H': 'Home Economics', 'M': 'Music',
    }
    wanted_group = group_aliases.get(group, group)
    ranked = []
    for customer in Customer.objects.only('id', 'username', 'fullName', 'group', 'settings'):
        if wanted_group and str(customer.group or '') != wanted_group:
            continue
        rows = _filtered_results(customer, period, level, subject)
        if not rows:
            continue
        score = round(sum(_number(row.get('score')) for row in rows) / len(rows))
        correct = sum(max(0, _integer(row.get('correct'))) for row in rows)
        ranked.append((score, correct, len(rows), customer))
    ranked.sort(key=lambda row: (-row[0], -row[1], -row[2], row[3].fullName or row[3].username))
    return ranked


def _normalized_result(payload):
        """Validate and normalize one browser/server exam result."""
        total = max(0, _integer(payload.get('total')))
        correct = max(0, min(total, _integer(payload.get('correct'))))
        score = max(0, min(100, round(_number(payload.get('score')))))
        set_id = _integer(payload.get('setId'))
        if set_id <= 0 or total <= 0:
            raise ValueError('setId and a positive total are required')
        attempted_at = parse_datetime(str(payload.get('at') or '')) or timezone.now()
        if timezone.is_naive(attempted_at):
            attempted_at = timezone.make_aware(attempted_at, timezone.get_current_timezone())
        attempt_id = str(payload.get('attemptId') or '').strip()[:80]
        if not attempt_id:
            attempt_id = 'legacy:%s:%s:%s:%s:%s' % (
                set_id, attempted_at.isoformat(), score, correct, total,
            )
        return {
            'attemptId': attempt_id,
            'setId': set_id,
            'setName': str(payload.get('setName') or '')[:255],
            'score': score,
            'correct': correct,
            'total': total,
            'subjectTr': str(payload.get('subjectTr') or '')[:255],
            'levelTr': str(payload.get('levelTr') or '')[:100],
            'classLevel': str(payload.get('classLevel') or '')[:50],
            'setKey': str(payload.get('setKey') or '')[:100],
            'examType': str(payload.get('examType') or '')[:50],
            'examMode': str(payload.get('examMode') or 'regular')[:20],
            'examVariant': str(payload.get('examVariant') or '')[:32],
            'completed': payload.get('completed', True) is not False,
            'at': attempted_at.isoformat(),
        }


class StudentExamResultsView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({'results': _results(request.user)})

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        submitted = payload.get('results') if isinstance(payload.get('results'), list) else [payload]
        if len(submitted) > MAX_RESULTS:
            return Response({'error': 'Too many results in one request'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            normalized = [_normalized_result(item) for item in submitted if isinstance(item, dict)]
        except ValueError as error:
            return Response({'error': str(error)}, status=status.HTTP_400_BAD_REQUEST)
        if not normalized:
            return Response({'saved': True, 'added': 0, 'results': []})

        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=request.user.pk)
            data = _settings(customer.settings).copy()
            rows = _results(customer)
            known_ids = {str(row.get('attemptId') or '') for row in rows}
            added = [row for row in normalized if row['attemptId'] not in known_ids]
            if not added:
                return Response({
                    'saved': True,
                    'duplicate': True,
                    'added': 0,
                    'result': normalized[0] if len(normalized) == 1 else None,
                    'results': normalized,
                })
            data[RESULTS_KEY] = (added + rows)[:MAX_RESULTS]
            data[ACTIVITY_KEY] = _activity(customer)
            customer.settings = data
            customer.save(update_fields=['settings'])
        return Response({
            'saved': True,
            'added': len(added),
            'result': normalized[0] if len(normalized) == 1 else None,
            'results': normalized,
        }, status=status.HTTP_201_CREATED)


class StudentStatsView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        summary = _summary(request.user, touch=True)
        ranked = _ranked_customers()
        summary['currentRank'] = next(
            (index for index, row in enumerate(ranked, 1) if row[3].pk == request.user.pk), 0
        )
        return Response(summary)


def _report(customer, period, level=''):
    rows = _filtered_results(customer, period, level)
    scores = [_number(row.get('score')) for row in rows]
    by_subject = defaultdict(list)
    for row in rows:
        by_subject[str(row.get('subjectTr') or 'Unspecified')].append(_number(row.get('score')))
    midpoint = len(scores) // 2
    older = scores[midpoint:]
    newer = scores[:midpoint] if midpoint else scores
    old_average = sum(older) / len(older) if older else 0
    new_average = sum(newer) / len(newer) if newer else 0
    weakest = min(by_subject.items(), key=lambda item: sum(item[1]) / len(item[1]), default=None)
    recommendations = []
    if not rows:
        recommendations.append('Complete an exam to start building your performance report.')
    elif weakest and sum(weakest[1]) / len(weakest[1]) < 70:
        recommendations.append('Review %s and retake a related practice exam.' % weakest[0])
    else:
        recommendations.append('Keep practising regularly to maintain your progress.')
    return {
        'period': period,
        'totalExams': len(rows),
        'averageScore': round(sum(scores) / len(scores)) if scores else 0,
        'bestScore': round(max(scores)) if scores else 0,
        'improvement': round(new_average - old_average) if older and newer else 0,
        'subjectBreakdown': [
            {
                'name': name,
                'exams': len(values),
                'averageScore': round(sum(values) / len(values)),
                'bestScore': round(max(values)),
            }
            for name, values in sorted(by_subject.items())
        ],
        'recommendations': recommendations,
    }


class StudentReportView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = str(request.query_params.get('period') or 'weekly')
        level = str(request.query_params.get('level') or '')
        return Response(_report(request.user, period, level))


class StudentReportExportView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not REPORTLAB_AVAILABLE:
            return Response({'error': 'PDF export is unavailable'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        period = str(request.query_params.get('period') or 'weekly')
        level = str(request.query_params.get('level') or '')
        report = _report(request.user, period, level)
        stream = BytesIO()
        pdf = canvas.Canvas(stream, pagesize=A4)
        font = _get_pdf_bengali_font() or 'Helvetica'
        width, height = A4
        y = height - 52
        lines = [
            'Cheradip Student Performance Report',
            'Student: %s' % (request.user.fullName or request.user.username),
            'Period: %s' % period,
            'Total exams: %s' % report['totalExams'],
            'Average score: %s%%' % report['averageScore'],
            'Best score: %s%%' % report['bestScore'],
            'Improvement: %s%%' % report['improvement'],
            '',
            'Subject performance',
        ]
        lines.extend(
            '%s - %s exams, average %s%%, best %s%%' %
            (row['name'], row['exams'], row['averageScore'], row['bestScore'])
            for row in report['subjectBreakdown']
        )
        for line in lines:
            if y < 45:
                pdf.showPage()
                y = height - 52
            pdf.setFont(font, 13 if y == height - 52 else 10)
            pdf.drawString(42, y, str(line)[:105])
            y -= 21
        pdf.save()
        response = HttpResponse(stream.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="student-report-%s.pdf"' % period
        return response


class StudentLeaderboardView(APIView):
    authentication_classes = [BearerTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = str(request.query_params.get('period') or 'all-time')
        level = str(request.query_params.get('level') or '')
        subject = str(request.query_params.get('subject') or '')
        group = str(request.query_params.get('group') or '')
        limit = max(1, min(100, _integer(request.query_params.get('limit'), 50)))
        ranked = _ranked_customers(period, level, subject, group)
        leaderboard = [
            {
                'rank': index,
                'name': row[3].fullName or row[3].username,
                'score': row[0],
                'exams': row[2],
                'is_current_user': row[3].pk == request.user.pk,
            }
            for index, row in enumerate(ranked[:limit], 1)
        ]
        user_rank = next(
            (index for index, row in enumerate(ranked, 1) if row[3].pk == request.user.pk), 0
        )
        return Response({'leaderboard': leaderboard, 'user_rank': user_rank})
