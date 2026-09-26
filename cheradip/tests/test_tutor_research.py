from unittest.mock import patch
from django.test import SimpleTestCase
from django.core.cache import cache
from cheradip.tutor_reference_digest import digest
from cheradip.tutor_inference import chat_body
from cheradip.tutor_web import public_url


class ResearchTests(SimpleTestCase):
    @patch('cheradip.tutor_reference_digest.complete', return_value='Reviewed source facts.')
    @patch('cheradip.tutor_reference_digest.cache', cache)
    def test_all_records_are_reviewed_and_digest_is_cached(self, complete):
        cache.clear()
        blocks = [f'[Q{i}] ' + 'An explanation with details. ' * 30 for i in range(97)]
        knowledge = {'text': '\n\n'.join(blocks), 'blocks': blocks, 'count': 97}
        def consume():
            generator = digest(knowledge, 'test', 'http://home')
            while True:
                try:
                    next(generator)
                except StopIteration as result:
                    return result.value
        result = consume()
        reviewed = '\n'.join(call.args[0]['messages'][-1]['content'] for call in complete.call_args_list)
        for i in range(97):
            self.assertIn(f'[Q{i}] ', reviewed)
        count = complete.call_count
        self.assertEqual(consume(), result)
        self.assertEqual(complete.call_count, count)

    def test_structured_chat_keeps_roles_and_generation_limits(self):
        messages = [{'role':'system','content':'Tutor'}, {'role':'user','content':'Question'}]
        body = chat_body({'model':'qwen','messages':messages,'file_context':[{'path':'References','content':'Data'}]}, True)
        self.assertEqual(body['messages'][0]['role'], 'system')
        self.assertEqual(body['messages'][-1], messages[-1])
        self.assertIn('Data', body['messages'][1]['content'])
        self.assertEqual(len(messages), 2)
        self.assertGreater(body['options']['repeat_penalty'], 1)

    @patch('cheradip.tutor_web.socket.getaddrinfo')
    def test_web_blocks_private_and_mixed_dns_addresses(self, dns):
        for address in ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1']:
            dns.return_value = [(2,1,6,'',(address,443))]
            self.assertFalse(public_url('https://example.com/article'))
        dns.return_value = [(2,1,6,'',('93.184.216.34',443))]
        self.assertTrue(public_url('https://example.com/article'))
        self.assertFalse(public_url('file:///secret'))
        self.assertFalse(public_url('https://user:password@example.com'))

