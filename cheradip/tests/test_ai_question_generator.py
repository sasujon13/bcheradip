"""Provider-order tests for AI-created exam questions."""
from unittest import mock

from django.test import SimpleTestCase

from cheradip import ai_question_generator as generator


VALID_QUESTION = {
    'question': 'Which answer is correct?',
    'option_1': 'Correct',
    'option_2': 'Wrong',
    'option_3': 'Other',
    'option_4': 'None',
    'answer': 'Correct',
    'explanation': 'Correct is the supplied correct answer.',
}


class AIQuestionProviderOrderTests(SimpleTestCase):
    def test_cloud_ai_is_used_first(self):
        with mock.patch.object(generator, '_call_cloud_ai', return_value=[VALID_QUESTION]) as cloud, \
             mock.patch.object(generator, '_call_home_ai') as home:
            questions, provider = generator.generate_questions_from_ai(
                subject_tr='English', count=1)
        cloud.assert_called_once()
        home.assert_not_called()
        self.assertEqual(provider, 'cloud')
        self.assertEqual(len(questions), 1)

    def test_home_ai_is_the_fallback(self):
        with mock.patch.object(generator, '_call_cloud_ai', return_value=None), \
             mock.patch.object(generator, '_call_home_ai', return_value=[VALID_QUESTION]) as home:
            questions, provider = generator.generate_questions_from_ai(
                subject_tr='English', count=1)
        home.assert_called_once()
        self.assertEqual(provider, 'home-ai')
        self.assertEqual(len(questions), 1)

    def test_invalid_cloud_reply_also_falls_back_to_home(self):
        with mock.patch.object(generator, '_call_cloud_ai', return_value=[{'question': 'Broken'}]), \
             mock.patch.object(generator, '_call_home_ai', return_value=[VALID_QUESTION]) as home:
            questions, provider = generator.generate_questions_from_ai(
                subject_tr='English', count=1)
        home.assert_called_once()
        self.assertEqual(provider, 'home-ai')
        self.assertEqual(len(questions), 1)
