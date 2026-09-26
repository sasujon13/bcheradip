"""Exercise both exam actions without changing stored questions or exams."""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from cheradip import exam_actions


class ExamCursor:
    def __init__(self, has_type=True):
        self.has_type = has_type
        self.rows = []
        self.inserts = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params=None):
        # MySQL drivers apply Python percent interpolation when params exist.
        # Literal LIKE wildcards must survive that separate formatting pass.
        if params is not None:
            sql % tuple(params)
        self.rows = []
        if 'information_schema.tables' in sql:
            self.rows = [(1,)]
        elif 'information_schema.columns' in sql:
            self.rows = [(int(self.has_type),)]
        elif sql.startswith('SELECT COUNT(*)'):
            self.rows = [(0,)]
        elif sql.startswith('SELECT DISTINCT chapter_no, topic_no'):
            self.rows = [('5', '1', 'Variables')]
        elif sql.startswith('SELECT DISTINCT chapter_no, chapter'):
            self.rows = [('5', 'Programming')]
        elif sql.startswith('SELECT qid, question, answer'):
            self.rows = [('q1', 'First question', 'First answer'),
                         ('q2', 'Second question', 'Second answer')]
        elif sql.startswith('SELECT qid'):
            self.rows = [('q1',), ('q2',)]
        elif sql.startswith('INSERT INTO cheradip_exam_set'):
            self.inserts.append((sql, params))

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


@override_settings(EXAM_AI_FILL_ENABLED=False)
class ExamActionTests(SimpleTestCase):
    def test_create_and_add_with_and_without_chapter_and_type_column(self):
        for action in (exam_actions.run_create_exam, exam_actions.run_add_exam):
            for chapter in ('', '5'):
                for has_type in (True, False):
                    with self.subTest(action=action.__name__, chapter=chapter, has_type=has_type):
                        cursor = ExamCursor(has_type)
                        conn = Mock()
                        conn.cursor.return_value = cursor
                        with patch.object(exam_actions, 'connections', {'hsc': conn}), \
                             patch.object(exam_actions, '_get_subject_scope', return_value=[
                                 ('Higher Secondary', '11-12', 'ICT', 2)]):
                            result = action('hsc', {'chapter': chapter})
                        self.assertEqual(len(cursor.inserts), 3, result)
                        conn.commit.assert_called_once()
                        conn.rollback.assert_not_called()

    def test_mcq_wildcards_keep_the_same_matching_pattern(self):
        condition = exam_actions._mcq_condition(ExamCursor(), 'questions')
        rendered = ('SELECT %s WHERE ' + condition) % (1,)
        self.assertIn("LIKE '%বহুনির্বাচনি%'", rendered)
