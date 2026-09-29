"""Exercise both exam actions without changing stored questions or exams."""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from cheradip import exam_actions


class ExamCursor:
    def __init__(self, has_type=True, active_live_count=0, practice_variants=None):
        self.has_type = has_type
        self.active_live_count = active_live_count
        self.practice_variants = practice_variants or []
        self.rows = []
        self.inserts = []
        self.question_inserts = []
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
        elif sql.startswith('SELECT COUNT(*)') and "exam_mode = 'live'" in sql:
            self.rows = [(self.active_live_count,)]
        elif sql.startswith('SELECT COUNT(*)'):
            self.rows = [(0,)]
        elif sql.startswith('SELECT exam_variant'):
            self.rows = [(variant,) for variant in self.practice_variants]
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
        elif sql.startswith('INSERT INTO `'):
            self.question_inserts.append((sql, params))

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

    def test_live_and_practice_actions_create_distinct_exam_modes(self):
        for action, expected_count, mode in (
            (exam_actions.run_create_live_exam, 1, "'live'"),
            (exam_actions.run_add_live_exam, 1, "'live'"),
            (exam_actions.run_create_practice_exam, 3, "'practice'"),
            (exam_actions.run_add_practice_exam, 3, "'practice'"),
        ):
            with self.subTest(action=action.__name__):
                cursor = ExamCursor()
                conn = Mock()
                conn.cursor.return_value = cursor
                with patch.object(exam_actions, 'connections', {'hsc': conn}), \
                     patch.object(exam_actions, '_get_subject_scope', return_value=[
                         ('Higher Secondary', '11-12', 'ICT', 30)]), \
                     patch.object(exam_actions, '_selected_question_qids', return_value=[
                         'q%s' % i for i in range(1, 121)
                     ]), \
                     patch.object(exam_actions, '_fill_practice_question_qids', return_value=(
                         ['q%s' % i for i in range(1, 121)], 0
                     )):
                    result = action('hsc', {})
                self.assertEqual(len(cursor.inserts), expected_count, result)
                self.assertTrue(all(mode in sql for sql, _params in cursor.inserts))
                conn.commit.assert_called_once()
                conn.rollback.assert_not_called()

        practice_counts = [params[-2] for _sql, params in cursor.inserts]
        self.assertEqual(practice_counts, [25, 50, 100])
        practice_durations = [params[-3] for _sql, params in cursor.inserts]
        self.assertEqual(practice_durations, [20, 40, 80])

    def test_add_live_and_practice_preserve_existing_papers(self):
        scope = [('Higher Secondary', '11-12', 'ICT', 30)]

        live_cursor = ExamCursor(active_live_count=1)
        live_conn = Mock()
        live_conn.cursor.return_value = live_cursor
        with patch.object(exam_actions, 'connections', {'hsc': live_conn}), \
             patch.object(exam_actions, '_get_subject_scope', return_value=scope), \
             patch.object(exam_actions, '_selected_question_qids', return_value=['q%s' % i for i in range(30)]):
            result = exam_actions.run_add_live_exam('hsc', {})
        self.assertEqual(live_cursor.inserts, [], result)
        self.assertIn('kept 1', result['message'])

        practice_cursor = ExamCursor(practice_variants=['short', 'middle'])
        practice_conn = Mock()
        practice_conn.cursor.return_value = practice_cursor
        with patch.object(exam_actions, 'connections', {'hsc': practice_conn}), \
             patch.object(exam_actions, '_get_subject_scope', return_value=scope), \
             patch.object(exam_actions, '_fill_practice_question_qids', return_value=(
                 ['q%s' % i for i in range(100)], 0
             )):
            result = exam_actions.run_add_practice_exam('hsc', {})
        self.assertEqual(len(practice_cursor.inserts), 1, result)
        self.assertEqual(practice_cursor.inserts[0][1][5], 'hard')
        self.assertIn('kept 2', result['message'])

    @override_settings(EXAM_AI_FILL_ENABLED=True)
    def test_practice_ai_fill_persists_complete_unique_mcqs(self):
        cursor = ExamCursor()
        existing = [
            {
                'qid': 'existing-%s' % i,
                'question': 'Existing question %s' % i,
                'answer': 'Existing answer %s' % i,
                'chapter_no': '1', 'chapter': 'Chapter',
                'topic_no': '1', 'topic': 'Topic',
            }
            for i in range(20)
        ]
        sequence = iter(range(20, 100))

        def generate(**kwargs):
            batch = []
            for _ in range(kwargs['count']):
                number = next(sequence)
                batch.append({
                    'question': 'AI question %s' % number,
                    'option_1': 'Correct %s' % number,
                    'option_2': 'Wrong A %s' % number,
                    'option_3': 'Wrong B %s' % number,
                    'option_4': 'Wrong C %s' % number,
                    'answer': 'Correct %s' % number,
                    'explanation': 'Explanation %s' % number,
                })
            return batch, 'home-ai'

        qid_sequence = iter('ai-%s' % i for i in range(80))
        with patch.object(exam_actions, '_selected_question_rows', return_value=existing), \
             patch.object(exam_actions, 'generate_questions_from_ai', side_effect=generate), \
             patch.object(exam_actions, 'next_qid_for_chapter_topic', side_effect=lambda *a, **k: next(qid_sequence)):
            qids, created = exam_actions._fill_practice_question_qids(
                cursor, 'hsc', 'cheradip_hsc_ict', 'Higher Secondary', '11-12',
                'ICT', [], [], target=100,
            )
        self.assertEqual(len(qids), 100)
        self.assertEqual(len(set(qids)), 100)
        self.assertEqual(created, 80)
        self.assertEqual(len(cursor.question_inserts), 80)
        self.assertTrue(all(params[12].startswith('Explanation ') for _sql, params in cursor.question_inserts))
