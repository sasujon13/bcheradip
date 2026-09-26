import json
from unittest.mock import patch
from django.test import SimpleTestCase, override_settings
from cheradip.tutor_clarification import clarification


@override_settings(TUTOR_OLLAMA_URL='')
class ClarificationTests(SimpleTestCase):
    def setUp(self):
        self.payload = {'model': 'auto', 'messages': [
            {'role': 'system', 'content': 'answer policy'},
            {'role': 'user', 'content': 'জীবন'}]}

    @patch('cheradip.tutor_clarification.requests.post')
    def test_valid_card_and_continuity(self, post):
        post.return_value.json.return_value = {'content': json.dumps({
            'clarify': True, 'question': 'কোন অর্থ?', 'options': ['কবিতা', 'জীববিজ্ঞান'], 'multi': False})}
        card = clarification(self.payload, {}, 'http://home')
        self.assertTrue(card.startswith('```cheradip-ask'))
        self.assertIn('কবিতা', card)
        messages = post.call_args.kwargs['json']['messages']
        self.assertEqual(sum(m['role'] == 'system' for m in messages), 1)
        self.assertEqual(messages[-1], self.payload['messages'][-1])

    @patch('cheradip.tutor_clarification.requests.post')
    def test_selected_topic_skips_check(self, post):
        self.assertIsNone(clarification(self.payload, {'selected_topic': True}, 'http://home'))
        post.assert_not_called()

    @patch('cheradip.tutor_clarification.requests.post')
    def test_clear_or_malformed_output_uses_normal_answer(self, post):
        for raw in ['{"clarify":false}', 'invalid', '[]', '{"clarify":true,"question":"Which?","options":[1,2]}']:
            post.return_value.json.return_value = {'content': raw}
            self.assertIsNone(clarification(self.payload, {}, 'http://home'))
