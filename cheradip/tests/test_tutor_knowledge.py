from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.core.cache import cache
from django.test import SimpleTestCase
from cheradip import tutor_knowledge as knowledge
from cheradip import tutor_routing as routing


SOURCE = dict(db_alias='hsc', table_name='cheradip_higher_secon_11_12_ict', level_tr='Higher Secondary', class_level='11-12',
              subject_tr='ICT', chapter='HTML', chapter_no='4', topic='টেবিল')


class KnowledgeTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_cleaning_preserves_code_math_and_draft_text(self):
        self.assertEqual(knowledge.plain('<p>&lt;td&gt; is a cell</p>'), '<td> is a cell')
        self.assertEqual(knowledge.plain('<td>'), '<td>')
        self.assertEqual(knowledge.plain('#include <stdio.h>'), '#include <stdio.h>')
        self.assertEqual(knowledge.plain('{"blocks":[{"text":"বাংলা explanation"}]}'), 'বাংলা explanation')

    def test_reference_budget_options_and_all_explanations(self):
        rows = [{'_source': SOURCE, 'qid': str(i), 'question': 'Question ' + str(i), 'answer': 'A',
                 'option_1': 'Correct option', 'explanation': 'Reason', 'explanation2': 'More detail', 'explanation3': 'Example'} for i in range(20)]
        result = knowledge.render_records(rows + rows)
        self.assertEqual(result['count'], 20)
        self.assertEqual(len(result['blocks']), 20)
        self.assertIn('option_1: Correct option', result['text'])
        self.assertIn('explanation3: Example', result['text'])

    def test_empty_and_unanswered_questions_are_not_evidence(self):
        self.assertEqual(knowledge.render_records([{'_source': SOURCE, 'qid': '1', 'question': 'No answer'}])['count'], 0)
        self.assertEqual(knowledge.render_records([{'_source': SOURCE, 'qid': '1', 'question': 'Bad answer', 'answer': '@' * 50}])['count'], 0)

    @patch('cheradip.tutor_knowledge.question_rows')
    @patch('cheradip.tutor_knowledge.topic_candidates')
    def test_cache_avoids_repeat_lookup_and_is_scoped(self, candidates, rows):
        candidates.return_value = [SimpleNamespace(**SOURCE)]
        rows.return_value = [{'_source': SOURCE, 'qid': '1', 'question': 'Table?', 'answer': 'A'}]
        scope = dict(level_tr='Higher Secondary', selected_topic=True, topic='টেবিল')
        self.assertFalse(knowledge.retrieve('টেবিল', scope)['cached'])
        self.assertTrue(knowledge.retrieve('টেবিল', scope)['cached'])
        self.assertEqual(rows.call_count, 1)
        knowledge.retrieve('টেবিল', {**scope, 'level_tr': 'Secondary'})
        self.assertEqual(rows.call_count, 2)

    @patch('cheradip.tutor_knowledge.fallback_source', return_value=None)
    @patch('cheradip.tutor_knowledge.topic_candidates', return_value=[])
    def test_unmatched_query_does_not_use_popular_unrelated_questions(self, candidates, fallback):
        self.assertEqual(knowledge.retrieve('volcanoes', {})['count'], 0)

    @patch('cheradip.tutor_knowledge.source_columns', return_value={'qid', 'question', 'answer', 'chapter_no', 'topic'})
    def test_filter_values_are_bound_and_only_allowed_tables_are_used(self, columns):
        cursor = Mock(); cursor.fetchall.return_value = []
        conn = Mock(); conn.cursor.return_value.__enter__ = Mock(return_value=cursor); conn.cursor.return_value.__exit__ = Mock(return_value=False)
        with patch('cheradip.tutor_knowledge.connections', {'hsc': conn}):
            malicious = "x' OR 1=1 --"
            knowledge.question_rows({**SOURCE, 'topic': malicious}, [])
            sql, values = cursor.execute.call_args.args
            self.assertNotIn(malicious, sql)
            self.assertIn(malicious, values)
            cursor.reset_mock()
            self.assertEqual(knowledge.question_rows({**SOURCE, 'table_name': 'users; DROP TABLE users'}, []), [])
            cursor.execute.assert_not_called()

    def test_scope_and_bilingual_terms(self):
        self.assertIn('টেবিল', knowledge.terms('Discuss Details on Explain HTML tables'))
        self.assertNotIn('আলোচনা', knowledge.terms('বিস্তারিত আলোচনা করুন: টেবিল'))
        with self.assertRaises(ValueError):
            knowledge.clean_scope({'topic': ['not a string']})


class RoutingTests(SimpleTestCase):
    def payload(self, model='auto'):
        return {'model': model, 'messages': [{'role': 'system', 'content': 'Tutor policy'}, {'role': 'user', 'content': 'Question'}], 'file_context': [], 'stream': True}

    @patch('cheradip.tutor_routing.requests.post')
    @patch('cheradip.tutor_routing.available_models', return_value=[routing.FAST, routing.CODER, routing.REASONING])
    def test_simple_questions_use_one_fast_model_without_planning(self, available, post):
        payload = self.payload(); info = routing.route(payload, 'What is HTML?', 'http://home')
        self.assertEqual(payload['model'], routing.FAST)
        self.assertFalse(info['planned']); post.assert_not_called()

    @patch('cheradip.tutor_routing.requests.post')
    @patch('cheradip.tutor_routing.available_models', return_value=[routing.FAST, routing.CODER])
    def test_complex_coding_uses_bounded_planner_then_specialist(self, available, post):
        post.return_value.json.return_value = {'content': 'Outline: explain algorithm, show code, verify result'}
        payload = self.payload(); info = routing.route(payload, 'Implement a Python algorithm step by step', 'http://home')
        self.assertEqual(payload['model'], routing.CODER)
        self.assertTrue(info['planned'])
        self.assertEqual(info['planner_model'], routing.FAST)
        self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 256)
        self.assertIn('Outline:', payload['messages'][0]['content'])

    @patch('cheradip.tutor_routing.requests.post')
    @patch('cheradip.tutor_routing.available_models', return_value=[routing.FAST])
    def test_planner_failure_falls_back_to_direct_answer(self, available, post):
        import requests
        post.side_effect = requests.Timeout()
        payload = self.payload(); info = routing.route(payload, 'Prove this result step by step', 'http://home')
        self.assertFalse(info['planned']); self.assertEqual(payload['model'], routing.FAST)

    @patch('cheradip.tutor_routing.available_models')
    def test_explicit_model_is_respected(self, available):
        payload = self.payload('chosen-model'); routing.route(payload, 'Implement complex code', 'http://home')
        self.assertEqual(payload['model'], 'chosen-model'); available.assert_not_called()

    @patch('cheradip.tutor_routing.requests.post')
    @patch('cheradip.tutor_routing.available_models', return_value=[routing.FAST, routing.CODER])
    def test_corrupt_plan_is_not_added_to_answer_context(self, available, post):
        post.return_value.json.return_value = {'content': '@' * 80}
        payload = self.payload(); info = routing.route(payload, 'Implement Python code', 'http://home')
        self.assertFalse(info['planned'])
        self.assertNotIn('@@@@', str(payload))
