import asyncio
import json
import unittest
from unittest.mock import patch

import httpx

from app.errors import ModelUnavailable
from app.integrations.ollama import OllamaClient


class ResponseErrors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner=asyncio.Runner()

    @classmethod
    def tearDownClass(cls):
        cls.runner.close()

    def call(self,response,stream=False):
        real_client=httpx.AsyncClient
        self.attempts=0
        def handle(request):
            self.attempts+=1
            self.payload=json.loads(request.content)
            return response[self.attempts-1] if isinstance(response,list) else response
        def client(**kwargs):
            return real_client(transport=httpx.MockTransport(handle),**kwargs)
        async def run():
            async def preview(text):pass
            with patch('httpx.AsyncClient',client):
                return await OllamaClient()._chat([{'role':'user','content':'테스트'}],label='도구 선택',on_delta=preview if stream else None)
        return self.runner.run(run())

    def test_normal_request_disables_thinking_and_returns_content(self):
        result=self.call(httpx.Response(200,json={'message':{'content':'답변'},'done':True}))
        self.assertEqual(result,'답변')
        self.assertFalse(self.payload['think'])

    def test_thinking_only_length_limit_is_explained(self):
        with self.assertRaisesRegex(ModelUnavailable,'내부 추론'):
            self.call(httpx.Response(200,json={'message':{'content':'','thinking':'비공개 추론'},'done_reason':'length'}))

    def test_empty_body_is_not_reported_as_connection_failure(self):
        with self.assertRaisesRegex(ModelUnavailable,'본문이 비어'):
            self.call(httpx.Response(200,json={'message':{'content':''}}))
        self.assertEqual(self.attempts,2)

    def test_transient_empty_response_is_retried_once_and_recovers(self):
        result=self.call([httpx.Response(200,json={'message':{'content':''}}),httpx.Response(200,json={'message':{'content':'정상 답변'}})])
        self.assertEqual(result,'정상 답변');self.assertEqual(self.attempts,2)

    def test_malformed_body_is_classified(self):
        with self.assertRaisesRegex(ModelUnavailable,'응답 형식'):
            self.call(httpx.Response(200,json={'unexpected':True}))

    def test_stream_thinking_only_length_limit_is_explained(self):
        body='\n'.join(json.dumps(row) for row in [{'message':{'thinking':'숨겨진 추론'}},{'message':{'content':''},'done':True,'done_reason':'length'}])
        with self.assertRaisesRegex(ModelUnavailable,'내부 추론'):
            self.call(httpx.Response(200,text=body),stream=True)
