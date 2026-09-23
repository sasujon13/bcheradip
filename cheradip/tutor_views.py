"""AI Tutor chat search endpoint."""
import logging
from urllib.parse import quote

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import tutor_search
from .permissions import PublicAccess

logger = logging.getLogger(__name__)


def _topic_link(topic_row):
    """Deep link into the Angular question browser for a topic-index row."""
    subject_tr = (topic_row.get('subject_tr') or '').strip()
    chapter = (topic_row.get('chapter') or '').strip()
    if subject_tr and chapter:
        return '/question/{}/chapter/{}'.format(quote(subject_tr), quote(chapter))
    if subject_tr:
        return '/question/{}'.format(quote(subject_tr))
    return '/question'


def _question_link(topic_row, question):
    """Deep link to a single question (falls back to chapter, then subject)."""
    subject_tr = (topic_row.get('subject_tr') or '').strip()
    chapter = (topic_row.get('chapter') or '').strip()
    qid = (question.get('qid') or '').strip()
    if subject_tr and chapter and qid:
        return '/question/{}/chapter/{}/question/{}'.format(
            quote(subject_tr), quote(chapter), quote(qid)
        )
    return _topic_link(topic_row)


class TutorSearchView(APIView):
    """
    GET /api/tutor/search/?q=...&limit=...

    Searches cheradip_tutor_topic_index for topics matching the query and
    returns matching topics, related topics and a few sample questions.
    Falls back to popular topics when nothing matches so the chatbox always
    has something useful to suggest.
    """
    permission_classes = [PublicAccess]
    authentication_classes = []

    def get(self, request):
        query = (request.query_params.get('q') or '').strip()
        try:
            limit = max(1, min(20, int(request.query_params.get('limit', 8))))
        except (TypeError, ValueError):
            limit = 8

        matches = tutor_search.search(query, limit=limit) if query else []
        topics = [tutor_search.serialize_index_row(m) for m in matches]

        related = []
        questions = []
        best_topic_row = topics[0] if topics else {}
        if matches:
            best = matches[0]
            related = [tutor_search.serialize_index_row(m) for m in tutor_search.related_topics(best, limit=6)]
            questions = tutor_search.sample_questions(best, limit=4)
        else:
            # No match: suggest the most popular topics as a starting point.
            related = [tutor_search.serialize_index_row(m) for m in tutor_search.popular_topics(limit=8)]
            best_topic_row = related[0] if related else {}

        # Attach deep links.
        for t in topics:
            t['link'] = _topic_link(t)
        for t in related:
            t['link'] = _topic_link(t)
        for q in questions:
            q['link'] = _question_link(best_topic_row, q)

        return Response({
            'query': query,
            'topics': topics,
            'related_topics': related,
            'questions': questions,
        }, status=status.HTTP_200_OK)
