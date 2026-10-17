from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from cheradip.saved_question_edit import recover_saved_question_edit


class SavedQuestionRecoveryTests(SimpleTestCase):
    def catalog(self):
        return [('Higher Secondary', '11-12', 'Physics 1st Paper', 'পদার্থবিজ্ঞান ১ম পত্র', '174', 30)]

    def run_recovery(self, questions, catalog=None, source=None):
        obj = SimpleNamespace(name='Physics_1st_Paper_Chapter_1', questions=questions, layout_settings={})
        cursor = MagicMock()
        cursor.fetchall.side_effect = [
            [('sq',)], self.catalog() if catalog is None else catalog,
            [('qid',), ('question',), ('option_1',), ('type',)],
            [('q1', 'Recovered text', 'Option A', 'mcq')] if source is None else source,
        ]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        with patch('cheradip.saved_question_edit.connections', {'hsc': connection}):
            result = recover_saved_question_edit(obj, 'hsc')
        return result, obj, cursor

    def test_recovers_only_referenced_rows_and_never_modifies_saved_record(self):
        (questions, layout), original, cursor = self.run_recovery([{'qid': 'q1', 'question': '— (q1)', 'custom': 'keep'}])
        self.assertEqual(questions[0]['question'], 'Recovered text')
        self.assertEqual(questions[0]['custom'], 'keep')
        self.assertEqual(original.questions[0]['question'], '— (q1)')
        self.assertEqual(original.layout_settings, {})
        self.assertEqual(layout['creatorContext']['subject_tr'], 'Physics 1st Paper')
        self.assertEqual(cursor.execute.call_args.args[1], ['q1'])

    def test_does_not_guess_between_two_subject_tables(self):
        rows = self.catalog() + [('Secondary', '9-10', 'Physics 1st Paper', 'Physics', '100', 30)]
        with self.assertRaisesMessage(ValueError, 'could not be matched uniquely'):
            self.run_recovery([{'qid': 'q1', 'question': ''}], catalog=rows)

    def test_reports_missing_source_question_instead_of_emitting_placeholder(self):
        with self.assertRaisesMessage(ValueError, 'no longer available'):
            self.run_recovery([{'qid': 'q1', 'question': ''}], source=[])

    def test_preserves_full_manual_question_rows(self):
        obj = SimpleNamespace(name='Manual', questions=[{'qid': 'q1', 'question': 'My edited text'}],
                              layout_settings={'creatorContext': {'level_tr': 'Higher Secondary', 'class_level': '11-12', 'subject_tr': 'Physics 1st Paper'}})
        with patch('cheradip.saved_question_edit.connections', {}) as connections:
            questions, _ = recover_saved_question_edit(obj, 'hsc')
        self.assertEqual(questions, obj.questions)

    def test_does_not_replace_real_text_when_source_choices_are_missing(self):
        (questions, _), _, _ = self.run_recovery([{'qid': 'q1', 'question': 'Question', 'type': 'mcq', 'option_1': None}])
        self.assertIsNone(questions[0]['option_1'])
        self.assertEqual(questions[0]['question'], 'Question')
