import json
from unittest.mock import Mock
from django.test import SimpleTestCase
from cheradip.tutor_stream import checked_chunks, UnusableReply, unusable


class StreamTests(SimpleTestCase):
    def test_repeated_bengali_sentences_are_rejected_but_code_is_allowed(self):
        sentence = 'আপনার প্রশ্ন বা প্রয়োজন সম্পর্কে বিশেষ করে বলুন তাহলে আমি বিস্তারিত আলোচনা করতে পারি।'
        self.assertTrue(unusable((sentence + '\n\n') * 3))
        self.assertFalse(unusable(sentence * 2))
        self.assertFalse(unusable('```text\n' + (sentence + '\n') * 4 + '```'))

    def test_clarification_is_published_once_and_stops_before_more_prose(self):
        block = '```cheradip-ask\n' + json.dumps({'question': 'কোনটি?', 'options': ['কবিতা', 'গান'], 'multi': False}) + '\n```'
        upstream = Mock()
        upstream.iter_content.return_value = [
            ('data: ' + json.dumps({'content': char}) + '\n\n').encode() for char in block
        ] + [b'data: {"content":"unwanted extra answer"}\n\n']
        self.assertEqual(list(checked_chunks(upstream)), [block])

    def test_invalid_and_incomplete_clarification_are_rejected(self):
        for text in ['```cheradip-ask\n{}\n```', '```cheradip-ask\n{"question":']:
            upstream = Mock()
            upstream.iter_content.return_value = [('data: ' + json.dumps({'content': text}) + '\n\n').encode()]
            with self.assertRaises(UnusableReply):
                list(checked_chunks(upstream))

    def test_repetition_across_chunks_triggers_retry_signal(self):
        sentence = 'আপনার প্রশ্ন বা প্রয়োজন সম্পর্কে বিশেষ করে বলুন তাহলে আমি বিস্তারিত আলোচনা করতে পারি।\n'
        upstream = Mock()
        upstream.iter_content.return_value = [('data: ' + json.dumps({'content': sentence}) + '\n\n').encode()] * 10
        with self.assertRaises(UnusableReply):
            list(checked_chunks(upstream))

    def test_split_unicode_and_sse_frames_are_preserved(self):
        expected = 'বাংলা explanation with code: <td>'
        data = ('data: ' + json.dumps({'content': expected}, ensure_ascii=False) + '\n\n').encode()
        upstream = Mock(); upstream.iter_content.return_value = [data[i:i+1] for i in range(len(data))]
        self.assertEqual(''.join(checked_chunks(upstream)), expected)

    def test_repeated_symbols_across_frames_never_leak(self):
        upstream = Mock(); upstream.iter_content.return_value = [b'data: {"content":"@@@"}\n\n'] * 20
        published = []
        with self.assertRaises(UnusableReply):
            for text in checked_chunks(upstream):
                published.append(text)
        self.assertEqual(published, [])

    def test_normal_email_code_and_markdown_are_not_rejected(self):
        self.assertFalse(unusable('Email a@example.com; use @context.\n---\n```python\n@decorator\ndef f(): pass\n```'))

    def test_empty_reply_is_rejected(self):
        upstream = Mock(); upstream.iter_content.return_value = [b'data: [DONE]\n\n']
        with self.assertRaises(UnusableReply):
            list(checked_chunks(upstream))

    def test_english_dominant_answer_is_rejected_for_bengali_request(self):
        answer = ('This answer incorrectly continues in English. It explains the author, historical setting, '
                  'central theme, imagery, language, cultural background, important quotations, and conclusion '
                  'without using the Bengali language requested by the learner. Every heading and explanatory '
                  'paragraph remains in English even though the original lesson title was written in Bengali.')
        upstream = Mock()
        upstream.iter_content.return_value = [('data: ' + json.dumps({'content': answer}) + '\n\n').encode()]
        with self.assertRaisesRegex(UnusableReply, 'wrong language'):
            list(checked_chunks(upstream, expected_language='Bengali'))

    def test_bengali_answer_may_contain_limited_english_terms(self):
        answer = ('বঙ্গবাণী কবিতায় মাতৃভাষার প্রতি গভীর ভালোবাসা প্রকাশ করা হয়েছে। কবি বাংলা ভাষার '
                  'মর্যাদা রক্ষার প্রয়োজনীয়তা তুলে ধরেছেন। মাতৃভাষাকে অবহেলা করলে জাতির নিজস্ব পরিচয় দুর্বল '
                  'হয়ে যায়। তাই কবিতাটি পাঠককে নিজের ভাষা ও সংস্কৃতির প্রতি শ্রদ্ধাশীল হতে শেখায়। এখানে '
                  'language এবং culture শব্দ দুটি প্রয়োজনীয় পরিভাষা হিসেবে ব্যবহৃত হয়েছে।')
        upstream = Mock()
        upstream.iter_content.return_value = [('data: ' + json.dumps({'content': answer}, ensure_ascii=False) + '\n\n').encode()]
        self.assertEqual(''.join(checked_chunks(upstream, expected_language='Bengali')), answer)
