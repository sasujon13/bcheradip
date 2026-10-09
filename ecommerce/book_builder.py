import html
import io
import json
import re
import zipfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import connections
from django.utils.text import slugify

from cheradip.models import CreatedQuestionSet
from cheradip.subject_question_tables import subject_question_table_name

from .models import BookAsset


def _safe_name(value):
    return (slugify(value, allow_unicode=False) or 'cheradip-book')[:90]


def _question_set_questions(config):
    ids = config.get('question_set_ids') or []
    try:
        ids = [int(value) for value in ids]
    except (TypeError, ValueError):
        raise ValueError('question_set_ids must be a list of numeric IDs.')
    questions = []
    headers = []
    for question_set in CreatedQuestionSet.objects.using('default').filter(pk__in=ids).order_by('pk'):
        headers.append(question_set.question_header or question_set.name)
        if isinstance(question_set.questions, list):
            questions.extend(item for item in question_set.questions if isinstance(item, dict))
    return questions, headers


def _exam_set_questions(config):
    ids = config.get('exam_set_ids') or []
    try:
        ids = [int(value) for value in ids]
    except (TypeError, ValueError):
        raise ValueError('exam_set_ids must be a list of numeric IDs.')
    if not ids:
        return [], []
    if 'hsc' not in connections:
        raise ValueError('The HSC question database is not configured.')

    questions = []
    headers = []
    connection = connections['hsc']
    with connection.cursor() as cursor:
        for exam_id in ids:
            cursor.execute(
                "SELECT name_label, level_tr, class_level, subject_tr, qids_json "
                "FROM cheradip_exam_set WHERE id = %s AND db_alias = 'hsc'",
                [exam_id],
            )
            row = cursor.fetchone()
            if not row:
                continue
            name, level, class_level, subject, raw_qids = row
            headers.append(name or subject or f'Exam {exam_id}')
            try:
                qids = json.loads(raw_qids) if raw_qids else []
            except (TypeError, ValueError, json.JSONDecodeError):
                qids = []
            if not qids:
                continue
            table = subject_question_table_name(level or '', class_level or '', subject or '')
            safe_table = table.replace('`', '``')
            placeholders = ', '.join(['%s'] * len(qids))
            cursor.execute(f"SELECT * FROM `{safe_table}` WHERE qid IN ({placeholders})", qids)
            names = [column[0] for column in cursor.description]
            indexed = {str(item.get('qid')): item for item in (dict(zip(names, values)) for values in cursor.fetchall())}
            questions.extend(indexed[str(qid)] for qid in qids if str(qid) in indexed)
    return questions, headers


def collect_book_questions(book, source_config=None):
    config = source_config if isinstance(source_config, dict) else (book.source_config or {})
    questions = [item for item in (config.get('questions') or []) if isinstance(item, dict)]
    headers = []
    from_sets, set_headers = _question_set_questions(config)
    from_exams, exam_headers = _exam_set_questions(config)
    questions.extend(from_sets)
    questions.extend(from_exams)
    headers.extend(set_headers)
    headers.extend(exam_headers)
    if not questions:
        raise ValueError('No questions were found. Add question_set_ids, exam_set_ids, or questions in Source config.')
    return questions, headers


def _plain(value):
    text = re.sub(r'<br\s*/?>', '\n', str(value or ''), flags=re.I)
    return re.sub(r'<[^>]+>', '', text).strip()


def _html_document(book, questions, headers):
    blocks = []
    for index, question in enumerate(questions, 1):
        stem = question.get('question') or question.get('question_text') or question.get('stem') or ''
        options = []
        for key in ('option_1', 'option_2', 'option_3', 'option_4'):
            if question.get(key):
                options.append(f'<li>{html.escape(_plain(question[key]))}</li>')
        answer = question.get('answer') or ''
        explanation = question.get('explanation') or question.get('explanation1') or ''
        blocks.append(
            '<article class="question">'
            f'<h2>{index}. {html.escape(_plain(stem))}</h2>'
            f'<ol type="A">{"".join(options)}</ol>'
            f'<p class="answer"><strong>উত্তর:</strong> {html.escape(_plain(answer))}</p>'
            f'<p><strong>ব্যাখ্যা:</strong> {html.escape(_plain(explanation))}</p>'
            '</article>'
        )
    subtitle = book.subtitle or ' · '.join(headers[:3])
    return f'''<!doctype html>
<html lang="bn"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(book.title)}</title><style>
body{{font-family:"Noto Sans Bengali","Nirmala UI",sans-serif;color:#183b3b;max-width:860px;margin:auto;padding:42px;line-height:1.65}}
header{{border-bottom:4px solid #c59b20;margin-bottom:28px}} h1{{color:#007f7f;margin-bottom:4px}}
.subtitle{{color:#5e7070}} .question{{break-inside:avoid;border-bottom:1px solid #dbe8e8;padding:12px 0}}
.question h2{{font-size:1.05rem;font-weight:600}} .answer strong{{color:#007f7f}} footer{{margin-top:32px;color:#728080}}
</style></head><body><header><h1>{html.escape(book.title_bn or book.title)}</h1>
<p class="subtitle">{html.escape(subtitle)}</p><p>{html.escape(book.author)}</p></header>
{"".join(blocks)}<footer>Cheradip · শিক্ষা, অনুশীলন ও অগ্রগতি</footer></body></html>'''


def _epub_bytes(book, document_html):
    xhtml = re.sub(r'<!doctype html>', '<?xml version="1.0" encoding="utf-8"?>', document_html, count=1, flags=re.I)
    package = f'''<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="book-id">cheradip-{book.pk}</dc:identifier>
<dc:title>{html.escape(book.title)}</dc:title><dc:language>bn</dc:language><dc:creator>{html.escape(book.author or 'Cheradip')}</dc:creator></metadata>
<manifest><item id="content" href="content.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="content"/></spine></package>'''
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        archive.writestr('META-INF/container.xml', '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        archive.writestr('OEBPS/package.opf', package)
        archive.writestr('OEBPS/content.xhtml', xhtml)
    return target.getvalue()


def build_book_asset(job):
    """Build a downloadable publication immediately and attach it to the book."""
    job.status = 'building'
    job.progress = 10
    job.message = 'Collecting selected question and exam sets.'
    job.save(using='ecommerce', update_fields=['status', 'progress', 'message', 'updated_at'])
    try:
        questions, headers = collect_book_questions(job.book, job.source_config)
        title = job.book.title_bn or job.book.title
        name = _safe_name(job.book.title)
        fmt = job.output_format
        job.progress = 45
        job.message = f'Formatting {len(questions)} questions as {fmt.upper()}.'
        job.save(using='ecommerce', update_fields=['progress', 'message', 'updated_at'])

        if fmt == 'html':
            payload = _html_document(job.book, questions, headers).encode('utf-8')
            extension = 'html'
        elif fmt == 'epub':
            payload = _epub_bytes(job.book, _html_document(job.book, questions, headers))
            extension = 'epub'
        else:
            from cheradip.views import ExportQuestionsView
            exporter = ExportQuestionsView()
            if fmt == 'docx':
                stream = exporter._build_docx(
                    questions, title, 18, 16, 18, 16, 210, 297,
                    layout_columns=1, layout_settings=job.book.source_config,
                    raw_data=job.book.source_config,
                )
            else:
                stream = exporter._build_pdf(
                    questions, title, 18, 16, 0, 16, 210, 297,
                    layout_columns=1,
                )
            payload = stream.getvalue()
            extension = fmt

        asset = BookAsset(
            book=job.book, title=f'{job.book.title} ({fmt.upper()})',
            asset_type='ebook', file_format=fmt, is_primary=True, is_downloadable=True,
        )
        asset.file.save(f'{name}.{extension}', ContentFile(payload), save=False)
        asset.file_size = len(payload)
        asset.save(using='ecommerce')
        job.status = 'completed'
        job.progress = 100
        job.message = f'Created {fmt.upper()} with {len(questions)} questions.'
        job.result_asset = asset
        job.save(using='ecommerce', update_fields=['status', 'progress', 'message', 'result_asset', 'updated_at'])
        return asset
    except Exception as exc:
        job.status = 'failed'
        job.message = str(exc)
        job.save(using='ecommerce', update_fields=['status', 'message', 'updated_at'])
        raise
