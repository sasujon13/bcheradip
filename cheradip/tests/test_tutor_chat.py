import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from datetime import timedelta
from django.test import SimpleTestCase, override_settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from cheradip.tutor_chat import (TutorChatView, TutorModelsView, TutorProfileView,
                                 answer_conflicts_with_scope, cloud_provider_candidates,
                                 curriculum_web_prompt, profile_levels,
                                 subject_response_instruction, validated_chat)


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
        self.web = web.start(); self.addCleanup(web.stop)
        public = patch('cheradip.tutor_chat.tutor_web.public_education_context', return_value='')
        self.public = public.start(); self.addCleanup(public.stop)

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

    def test_web_prompt_uses_visible_subject_label(self):
        prompt = curriculum_web_prompt('বিস্তারিত আলোচনা করুন: বঙ্গবাণী', {
            'level_tr': 'Secondary', 'class_level': '9-10', 'subject_tr': 'Bengali',
            'subject_name': 'Bengali Cohort Text', 'chapter': 'কবিতা', 'topic': 'বঙ্গবাণী'})
        self.assertIn('Subject: Bengali Cohort Text', prompt)
        self.assertIn('Chapter: কবিতা', prompt)
        self.assertIn('Learner question:\nবিস্তারিত আলোচনা করুন: বঙ্গবাণী', prompt)
        self.assertIn('NON-ENGLISH SUBJECT RESPONSE FORMAT', prompt)

    def test_english_subject_requires_bengali_meanings_and_pronunciation(self):
        scope = {'subject_name': 'English 1st Paper', 'subject_tr': 'English',
                 'chapter': 'Seen passage', 'topic': 'The Greed of the Mighty Rivers'}
        instruction = subject_response_instruction(scope)
        self.assertIn('important English words with clear Bengali meanings', instruction)
        self.assertIn('Bengali-script pronunciation for every English sentence', instruction)
        self.assertIn('complete Bengali meaning of the entire', instruction)
        self.assertIn(instruction, curriculum_web_prompt('Discuss the passage', scope))

    def test_bengali_english_subject_name_is_detected(self):
        instruction = subject_response_instruction({'subject_name': 'ইংরেজি প্রথম পত্র'})
        self.assertIn('ENGLISH SUBJECT RESPONSE FORMAT', instruction)

    def test_other_subjects_allow_helpful_standard_english_terms(self):
        instruction = subject_response_instruction({'subject_name': 'তথ্য ও যোগাযোগ প্রযুক্তি'})
        self.assertIn('standard English word', instruction)
        self.assertIn('easier to understand', instruction)

    def test_grounded_fallback_rejects_a_poem_changed_into_a_story(self):
        scope = {'chapter': 'কবিতা', 'topic': 'জুতা আবিষ্কার'}
        self.assertTrue(answer_conflicts_with_scope('এই গল্পটি একজন শিক্ষকের কাহিনি।', scope))
        self.assertFalse(answer_conflicts_with_scope('এটি রবীন্দ্রনাথ ঠাকুরের ব্যঙ্গকবিতা।', scope))

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

    def test_follow_up_policy_uses_previous_exchange_and_selected_topic(self):
        result = validated_chat({'messages': [
            {'role': 'user', 'content': 'বিস্তারিত আলোচনা করুন: বঙ্গবাণী'},
            {'role': 'assistant', 'content': 'এটি একটি বাংলা কবিতা।'},
            {'role': 'user', 'content': 'কবি কে এবং কেন?'}]})
        policy = result['messages'][0]['content']
        self.assertIn('immediately preceding question and Tutor answer', policy)
        self.assertIn('keep the selected subject, chapter and topic', policy)

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

    @patch('cheradip.tutor_chat.cloud_provider_candidates', return_value=[
        {'provider': 'google', 'api_key': 'shared-key', 'model': 'gemini-3.8-flash'}])
    @patch('cheradip.tutor_chat.open_stream')
    def test_cloud_mode_searches_without_curriculum_match(self, open_ai, candidates):
        self.knowledge.return_value = {'text': '[Q1] explanation: must not be read', 'blocks': ['[Q1] explanation: must not be read'],
                                       'sources': [{'reference': 'Q1'}], 'count': 1, 'cached': False}
        upstream = Mock()
        upstream.iter_content.return_value = [b'data: {"content":"Answer"}\n\n']
        open_ai.return_value = upstream
        response = TutorChatView.as_view()(self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'আজকের বিজ্ঞান সংবাদ কী?'}],
            'preferences': {'accessMode': 'cloud', 'webSearch': True},
            'learning_context': {'level_tr': 'Secondary', 'class_level': '9-10', 'subject_tr': 'Bengali',
                                 'subject_name': 'Bengali Cohort Text', 'chapter': 'কবিতা',
                                 'topic': 'কাকতাড়ুয়া', 'selected_topic': True},
        }, format='json'))
        body = b''.join(response.streaming_content)
        self.assertIn(b'Answer', body)
        self.assertNotIn(b'Reading up to', body)
        self.assertNotIn(b'must not be read', str(open_ai.call_args.args[0]).encode())
        sent = open_ai.call_args.args[0]['messages'][-1]['content']
        self.assertIn('Subject: Bengali Cohort Text', sent)
        self.assertIn('Topic: কাকতাড়ুয়া', sent)
        self.assertEqual(open_ai.call_args.args[0]['model'], 'gemini-3.8-flash')
        self.knowledge.assert_not_called()
        self.web.assert_not_called()

    @patch('cheradip.tutor_chat.cloud_provider_candidates', return_value=[
        {'provider': 'anthropic', 'api_key': 'claude-key', 'model': 'claude-sonnet-4-20250514'},
        {'provider': 'google', 'api_key': 'google-key', 'model': 'gemini-3.8-flash'}])
    @patch('cheradip.tutor_chat.open_stream')
    def test_cloud_tries_every_provider_then_reports_daily_quota(self, open_ai, candidates):
        import requests
        open_ai.side_effect = [requests.HTTPError('credit exhausted'), requests.HTTPError('quota exhausted'),
                               requests.ConnectionError('home unavailable')]
        response = TutorChatView.as_view()(self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'বিস্তারিত আলোচনা করুন: কাকতাড়ুয়া'}],
            'preferences': {'accessMode': 'cloud', 'webSearch': False},
            'learning_context': {'level_tr': 'Secondary', 'class_level': '9-10', 'subject_tr': 'Bengali',
                                 'subject_name': 'Bengali Cohort Text', 'chapter': 'উপন্যাস',
                                 'topic': 'কাকতাড়ুয়া', 'selected_topic': True},
        }, format='json'))
        body = b''.join(response.streaming_content).decode()
        events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith('data: {')]
        content = ''.join(event.get('content', '') for event in events)
        self.assertIn('Search AI quota', content)
        self.assertNotIn('cheradip-ask', body)
        self.assertEqual(open_ai.call_count, 3)

    @patch('cheradip.tutor_chat.database_provider_key')
    @patch('cheradip.tutor_chat.customer_tutor_settings', return_value={
        'api_keys': {'openai': 'personal-openai-key'}})
    @patch('cheradip.tutor_chat.customer_from_request', return_value=object())
    def test_cloud_candidates_prefer_personal_key_then_shared_key(self, customer, settings, shared):
        shared.side_effect = lambda provider: 'shared-google-key' if provider == 'google' else ''
        candidates = {item['provider']: item for item in cloud_provider_candidates(self.factory.get('/'))}
        self.assertEqual(candidates['openai']['api_key'], 'personal-openai-key')
        self.assertEqual(candidates['google']['api_key'], 'shared-google-key')
        self.assertNotIn('openai', [call.args[0] for call in shared.call_args_list])

    @patch('cheradip.tutor_chat.resolve_provider_config', return_value={
        'provider': 'brave', 'api_key': 'brave-key'})
    @patch('cheradip.tutor_chat.open_stream')
    def test_search_mode_returns_one_clean_grounded_answer(self, open_ai, resolve):
        upstream = Mock()
        upstream.iter_content.return_value = [
            ('data: ' + json.dumps({'content': 'ব্রেভে যাচাই করা পরিষ্কার বাংলা উত্তর'}) + '\n\n').encode()
        ]
        open_ai.return_value = upstream
        self.knowledge.return_value = {'text': 'must not be read', 'blocks': ['must not be read'],
                                       'sources': [{'reference': 'Q1'}], 'count': 1, 'cached': False}
        response = TutorChatView.as_view()(self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'বিস্তারিত আলোচনা করুন: বঙ্গবাণী'}],
            'preferences': {'accessMode': 'search', 'webSearch': True},
            'learning_context': {'level_tr': 'Secondary', 'class_level': '9-10', 'subject_tr': 'Bengali',
                                 'subject_name': 'বাংলা সহপাঠ', 'chapter': 'কবিতা',
                                 'topic': 'বঙ্গবাণী', 'selected_topic': True},
        }, format='json'))
        body = b''.join(response.streaming_content).decode()
        events = [json.loads(line[6:]) for line in body.splitlines() if line.startswith('data: {')]
        content = ''.join(event.get('content', '') for event in events)
        self.assertIn('পরিষ্কার বাংলা উত্তর', content)
        self.assertNotIn('reference', content.lower())
        self.assertNotIn('http', content.lower())
        self.knowledge.assert_not_called()
        self.clarification.assert_not_called()
        self.web.assert_not_called()
        resolve.assert_called_once()
        config = open_ai.call_args.kwargs['provider_config']
        self.assertEqual(config['provider'], 'brave')
        self.assertNotIn('google_search', config)
        sent = open_ai.call_args.args[0]['messages'][-1]['content']
        self.assertIn('Level: Secondary', sent)
        self.assertIn('Class: 9-10', sent)
        self.assertIn('Subject: বাংলা সহপাঠ', sent)
        self.assertIn('Chapter: কবিতা', sent)
        self.assertIn('Topic: বঙ্গবাণী', sent)

    @patch('cheradip.tutor_chat.cloud_provider_candidates', return_value=[])
    @patch('cheradip.tutor_chat.resolve_provider_config', side_effect=lambda _request, incoming: {
        'provider': incoming['provider'], 'api_key': incoming['provider'] + '-key'})
    @patch('cheradip.tutor_chat.open_stream')
    def test_search_mode_reports_quota_without_clarification_card(self, open_ai, resolve, candidates):
        import requests
        open_ai.side_effect = requests.HTTPError('quota exhausted')
        response = TutorChatView.as_view()(self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'Explain photosynthesis'}],
            'preferences': {'accessMode': 'search', 'webSearch': False},
        }, format='json'))
        body = b''.join(response.streaming_content).decode()
        self.assertIn('All Search AI quotas are exhausted', body)
        self.assertNotIn('cheradip-ask', body)
        self.assertEqual(open_ai.call_count, 2)

    @patch('cheradip.tutor_chat.cloud_provider_candidates', return_value=[
        {'provider': 'google', 'api_key': 'google-key', 'model': 'gemini-2.5-flash'}])
    @patch('cheradip.tutor_chat.resolve_provider_config', side_effect=lambda _request, incoming: {
        'provider': incoming['provider'], 'api_key': incoming['provider'] + '-key'})
    @patch('cheradip.tutor_chat.open_stream')
    def test_search_mode_falls_back_from_brave_to_normal_gemini(self, open_ai, resolve, candidates):
        import requests
        gemini = Mock()
        gemini.iter_content.return_value = [
            b'data: {"content":"Clean Gemini API fallback answer"}\n\n']
        open_ai.side_effect = [requests.HTTPError('brave quota'), gemini]
        response = TutorChatView.as_view()(self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'Explain photosynthesis'}],
            'preferences': {'accessMode': 'search', 'webSearch': False},
        }, format='json'))
        body = b''.join(response.streaming_content).decode()
        self.assertIn('Clean Gemini API fallback answer', body)
        self.assertNotIn('cheradip-ask', body)
        self.assertEqual(open_ai.call_count, 2)
        config = open_ai.call_args.kwargs['provider_config']
        self.assertEqual(config['provider'], 'google')
        self.assertNotIn('google_search', config)

    @patch('cheradip.tutor_chat.resolve_provider_config', side_effect=lambda _request, incoming: {
        'provider': incoming['provider'], 'api_key': incoming['provider'] + '-personal-key'})
    @patch('cheradip.tutor_chat.open_stream')
    def test_cloud_manual_provider_and_model_are_tried_before_brave(self, open_ai, resolve):
        selected = Mock()
        selected.iter_content.return_value = [b'data: {"content":"Selected provider answer"}\n\n']
        open_ai.return_value = selected
        response = TutorChatView.as_view()(self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'Explain photosynthesis'}],
            'model': 'gemini-flash-latest',
            'preferences': {'accessMode': 'cloud', 'webSearch': False},
            'provider_config': {'provider': 'google', 'api_key': ''},
        }, format='json'))
        body = b''.join(response.streaming_content).decode()
        self.assertIn('Selected provider answer', body)
        self.assertEqual(open_ai.call_count, 1)
        self.assertEqual(open_ai.call_args.kwargs['provider_config']['provider'], 'google')
        self.assertEqual(open_ai.call_args.args[0]['model'], 'gemini-flash-latest')
        self.assertEqual(resolve.call_count, 1)
        self.assertEqual(resolve.call_args.args[1], {'provider': 'google', 'api_key': ''})

    @patch('cheradip.tutor_chat.resolve_provider_config', side_effect=lambda _request, incoming: {
        'provider': incoming['provider'], 'api_key': incoming['provider'] + '-key'})
    @patch('cheradip.tutor_chat.open_stream')
    def test_cloud_manual_failure_falls_back_to_brave(self, open_ai, resolve):
        import requests
        brave = Mock()
        brave.iter_content.return_value = [b'data: {"content":"Brave fallback answer"}\n\n']
        open_ai.side_effect = [requests.HTTPError('selected provider quota'), brave]
        response = TutorChatView.as_view()(self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'Explain photosynthesis'}],
            'model': 'gpt-4.1-mini',
            'preferences': {'accessMode': 'cloud', 'webSearch': False},
            'provider_config': {'provider': 'openai', 'api_key': ''},
        }, format='json'))
        body = b''.join(response.streaming_content).decode()
        self.assertIn('Brave fallback answer', body)
        self.assertEqual([call.kwargs['provider_config']['provider'] for call in open_ai.call_args_list],
                         ['openai', 'brave'])

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
        self.assertIn('openai', response.data['providers'])

    @patch('cheradip.tutor_chat.requests.get')
    def test_direct_provider_catalog_remains_available_when_home_ai_is_offline(self, get):
        import requests
        get.side_effect = requests.ConnectionError('offline')
        response = TutorModelsView.as_view()(self.factory.get('/'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('openai', response.data['providers'])
        self.assertIn('warning', response.data)

    @patch('cheradip.tutor_chat.key_status', return_value={
        'openai': {'personal': False, 'shared': True},
        'google': {'personal': False, 'shared': False},
    })
    @patch('cheradip.tutor_chat.requests.get')
    def test_models_identify_only_anonymous_shared_providers(self, get, status):
        get.return_value.json.return_value = {'models': [{'id': 'live-model'}]}
        response = TutorModelsView.as_view()(self.factory.get('/'))
        self.assertEqual(response.data['shared_providers'], ['openai'])

    def test_direct_provider_requires_its_api_key(self):
        request = self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'Hello'}],
            'provider_config': {'provider': 'openai', 'api_key': ''},
        }, format='json')
        response = TutorChatView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertIn('OpenAI API key', response.data['error'])

    @patch('cheradip.tutor_providers.requests.post')
    def test_direct_openai_key_drives_the_tutor_without_home_ai(self, post):
        upstream = Mock()
        upstream.json.return_value = {'choices': [{'message': {'content': 'Direct provider answer'}}]}
        post.return_value = upstream
        request = self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'Hello'}],
            'model': 'gpt-4.1-mini',
            'provider_config': {'provider': 'openai', 'api_key': 'sk-browser-test'},
        }, format='json')
        response = TutorChatView.as_view()(request)
        body = b''.join(response.streaming_content)
        self.assertIn(b'Direct provider answer', body)
        self.assertEqual(post.call_args.args[0], 'https://api.openai.com/v1/chat/completions')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer sk-browser-test')
        self.assertNotIn(b'sk-browser-test', body)

    @patch('cheradip.tutor_key_store.database_provider_key', return_value='server-shared-key')
    @patch('cheradip.tutor_providers.requests.post')
    def test_guest_can_use_shared_provider_without_login(self, post, shared):
        upstream = Mock()
        upstream.json.return_value = {'choices': [{'message': {'content': 'Anonymous answer'}}]}
        post.return_value = upstream
        request = self.factory.post('/', {
            'messages': [{'role': 'user', 'content': 'Hello'}],
            'model': 'gpt-4.1-mini',
            'provider_config': {'provider': 'openai', 'api_key': ''},
        }, format='json')
        response = TutorChatView.as_view()(request)
        self.assertIn(b'Anonymous answer', b''.join(response.streaming_content))
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer server-shared-key')
        shared.assert_called_once_with('openai')
