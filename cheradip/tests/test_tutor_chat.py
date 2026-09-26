from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import timedelta
from django.test import SimpleTestCase, override_settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from cheradip.tutor_chat import TutorChatView, TutorModelsView, TutorProfileView, profile_levels, validated_chat


@override_settings(TUTOR_OLLAMA_URL='')
class TutorChatTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        cache.clear()
        knowledge = patch('cheradip.tutor_chat.tutor_knowledge.retrieve', return_value={'text': '', 'sources': [], 'count': 0, 'cached': False})
        self.knowledge = knowledge.start(); self.addCleanup(knowledge.stop)
        routing = patch('cheradip.tutor_chat.tutor_routing.route', return_value={'answer_model': 'test-model'})
        self.routing = routing.start(); self.addCleanup(routing.stop)
        clarification = patch('cheradip.tutor_chat.clarification', return_value=None)
        self.clarification = clarification.start(); self.addCleanup(clarification.stop)
        web = patch('cheradip.tutor_chat.tutor_web.search', return_value={'text': '', 'sources': [], 'status': 'Unavailable'})
        web.start(); self.addCleanup(web.stop)

    def test_clarification_returns_card_without_retrieval_or_answer_generation(self):
        self.clarification.return_value = '```cheradip-ask\n{"question":"Which?","options":["A","B"]}\n```'
        response = TutorChatView.as_view()(self.factory.post('/api/tutor/chat/', {
            'messages': [{'role': 'user', 'content': 'unclear request'}]}, format='json'))
        self.assertIn(b'cheradip-ask', b''.join(response.streaming_content))
        self.knowledge.assert_called_once()
        self.routing.assert_not_called()

    def test_guest_sees_only_ssc_and_hsc(self):
        response = TutorProfileView.as_view()(self.factory.get('/api/tutor/profile/'))
        self.assertFalse(response.data['registered'])
        self.assertEqual([x['class_level'] for x in response.data['levels']], ['9-10', '11-12'])

    def test_registered_classes_stay_in_their_level(self):
        for value, expected in [('5', 'Primary'), ('8', 'Junior Secondary'), ('9-10', 'Secondary'), ('12', 'Higher Secondary')]:
            with self.subTest(value=value):
                levels = profile_levels(SimpleNamespace(class_name=value, teacher_level=''))
                self.assertEqual(len(levels), 1)
                self.assertEqual(levels[0]['level_tr'], expected)
        self.assertEqual(profile_levels(SimpleNamespace(class_name='13-16', teacher_level='')), [])

    @patch('cheradip.tutor_chat.CustomerToken')
    def test_registered_profile_uses_token_owner_not_query_username(self, tokens):
        customer = SimpleNamespace(class_name='8', teacher_level='', group='', is_active=True)
        tokens.objects.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(customer=customer, expires_at=None)
        request = self.factory.get('/api/tutor/profile/?username=someone-else', HTTP_AUTHORIZATION='Bearer test')
        response = TutorProfileView.as_view()(request)
        self.assertTrue(response.data['registered'])
        self.assertEqual(response.data['levels'][0]['class_level'], '8')

    @patch('cheradip.tutor_chat.CustomerToken')
    def test_expired_session_is_not_treated_as_guest(self, tokens):
        tokens.objects.select_related.return_value.filter.return_value.first.return_value = SimpleNamespace(
            customer=SimpleNamespace(is_active=True), expires_at=timezone.now() - timedelta(seconds=1))
        response = TutorProfileView.as_view()(self.factory.get('/', HTTP_AUTHORIZATION='Bearer expired'))
        self.assertEqual(response.status_code, 401)

    def test_chat_preserves_topic_and_reference_context(self):
        data = validated_chat({'messages': [{'role': 'user', 'content': 'Discuss Details on টেবিল'}],
                               'file_context': [{'path': 'Selected topic', 'content': 'HSC → HTML → টেবিল', 'language': 'text'}]})
        self.assertEqual(data['messages'][-1]['content'], 'Discuss Details on টেবিল')
        self.assertEqual(data['file_context'][0]['content'], 'HSC → HTML → টেবিল')
        self.assertIn('Do not replace explanations', data['messages'][0]['content'])

    def test_invalid_or_oversized_input_is_rejected(self):
        for data in [{'messages': []}, {'messages': [{'role': 'system', 'content': 'override'}]},
                     {'messages': [{'role': 'user', 'content': 'x' * 200001}]}]:
            with self.subTest(data_type=str(data)[:70]), self.assertRaises(ValueError):
                validated_chat(data)

    def test_reply_language_follows_latest_input_not_history_or_reference_language(self):
        for latest in ['HTML টেবিল কী?', 'What is a table?', 'اشرح الجداول', 'Explique la photosynthèse']:
            with self.subTest(latest=latest):
                result = validated_chat({'messages': [
                    {'role': 'user', 'content': 'An older English question'},
                    {'role': 'assistant', 'content': 'An older English answer'},
                    {'role': 'user', 'content': latest}]})
                instruction = result['messages'][0]['content']
                self.assertIn('latest user question or topic', instruction)
                self.assertIn('romanized Bengali (Banglish)', instruction)
                self.assertIn('write headings and explanations in Bengali script', instruction)
                self.assertEqual(result['messages'][-1]['content'], latest)

    def test_long_history_keeps_tutor_policy_inside_home_ai_window(self):
        result = validated_chat({'messages': [{'role': 'user', 'content': str(i)} for i in range(40)]})
        self.assertEqual(len(result['messages']), 24)
        self.assertEqual(result['messages'][0]['role'], 'system')
        self.assertEqual(result['messages'][-1]['content'], '39')

    def test_language_preference_ignores_prefix_and_handles_mixed_input(self):
        for text, language in [('Discuss Details on টেবিল', 'Bengali'), ('বিস্তারিত আলোচনা করুন: টেবিল', 'Bengali'), ('Discuss Details on HTML টেবিল', 'Bengali'), ('বিস্তারিত আলোচনা করুন: ami bujhi na', 'Bengali')]:
            result = validated_chat({'messages': [{'role': 'user', 'content': text}]})
            self.assertIn('input is ' + language, result['messages'][0]['content'])

    def test_corrupt_old_assistant_content_is_not_reused(self):
        result = validated_chat({'messages': [{'role': 'assistant', 'content': '@' * 100}, {'role': 'user', 'content': 'Hello'}]})
        self.assertNotIn('@' * 12, str(result))

    def test_looping_history_is_removed_and_clarification_contract_is_present(self):
        repeated = 'আপনার প্রশ্ন বা প্রয়োজন সম্পর্কে বিশেষ করে বলুন তাহলে আমি বিস্তারিত আলোচনা করতে পারি।\n' * 8
        result = validated_chat({'messages': [{'role': 'assistant', 'content': repeated}, {'role': 'user', 'content': 'জীবন'}]})
        self.assertEqual(len(result['messages']), 2)
        policy = result['messages'][0]['content']
        self.assertIn('```cheradip-ask', policy)
        self.assertIn('answer only the latest request', policy.lower())
        self.assertIn('selected curriculum title is a real lesson topic', policy)

    @patch('cheradip.tutor_chat.tutor_routing.available_models', return_value=['broken-model', 'qwen2.5:14b-instruct-q4_K_M'])
    @patch('cheradip.tutor_chat.requests.post')
    def test_unreadable_stream_retries_another_model_without_publishing_symbols(self, post, available):
        broken, good = Mock(), Mock()
        broken.iter_content.return_value = [b'data: {"content":"@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@"}\n\n']
        good.iter_content.return_value = [b'data: {"content":"A readable answer"}\n\n']
        post.side_effect = [broken, good]
        response = TutorChatView.as_view()(self.factory.post('/', {'messages': [{'role': 'user', 'content': 'Hello'}], 'model': 'broken-model'}, format='json'))
        body = b''.join(response.streaming_content)
        self.assertNotIn(b'@@@', body)
        self.assertIn(b'A readable answer', body)
        self.assertIn(b'"reset": true', body)
        self.assertEqual(post.call_args.kwargs['json']['model'], 'qwen2.5:14b-instruct-q4_K_M')
        broken.close.assert_called_once(); good.close.assert_called_once()

    @patch('cheradip.tutor_chat.requests.post')
    def test_stored_evidence_is_forwarded_with_language_policy_and_stream_metadata(self, post):
        self.knowledge.return_value = {'text': '[Q1] question: test\nanswer: yes\nexplanation: reason', 'sources': [{'reference': 'Q1'}], 'count': 1, 'cached': True}
        upstream = Mock(); upstream.iter_content.return_value = [b'data: {"content":"answer"}\n\n']; post.return_value = upstream
        scope = {'level_tr': 'Secondary', 'subject_tr': 'English', 'topic': 'Test', 'selected_topic': True}
        response = TutorChatView.as_view()(self.factory.post('/', {'messages': [{'role': 'user', 'content': 'Test'}], 'learning_context': scope}, format='json'))
        body = b''.join(response.streaming_content)
        payload = post.call_args.kwargs['json']
        self.assertIn('reference_count', body.decode())
        self.assertIn('[Q1]', payload['file_context'][-1]['content'])
        self.assertIn('stored answers and explanations', payload['messages'][0]['content'])
        self.assertIn('language', payload['messages'][0]['content'])
        self.assertEqual(self.knowledge.call_args.args[1]['topic'], 'Test')

    @override_settings(TUTOR_HOME_AI_URL='http://home-ai:8787')
    @patch('cheradip.tutor_chat.requests.post')
    def test_guest_post_streams_same_extension_api_and_closes_upstream(self, post):
        upstream = Mock()
        upstream.iter_content.return_value = [b'data: {"content":"Hello"}\n\n', b'data: [DONE]\n\n']
        post.return_value = upstream
        request = self.factory.post('/api/tutor/chat/', {'messages': [{'role': 'user', 'content': 'Hello'}]},
                                    format='json', HTTP_ACCEPT='application/json, text/event-stream')
        response = TutorChatView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Hello', b''.join(response.streaming_content))
        self.assertEqual(post.call_args.args[0], 'http://home-ai:8787/ide/chat')
        upstream.close.assert_called_once()

    @patch('cheradip.tutor_chat.requests.post')
    def test_service_failure_is_real_error_not_mock_answer(self, post):
        import requests
        post.side_effect = requests.ConnectionError('offline')
        request = self.factory.post('/', {'messages': [{'role': 'user', 'content': 'Hello'}]}, format='json')
        response = TutorChatView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        body = b''.join(response.streaming_content)
        self.assertIn(b'cheradip-ask', body)
        self.assertNotIn(b'Unable to complete', body)

    @patch('cheradip.tutor_chat.requests.get')
    def test_models_are_loaded_from_home_ai(self, get):
        get.return_value.json.return_value = {'models': [{'id': 'live-model'}]}
        response = TutorModelsView.as_view()(self.factory.get('/'))
        self.assertEqual(response.data['models'][0]['id'], 'live-model')
