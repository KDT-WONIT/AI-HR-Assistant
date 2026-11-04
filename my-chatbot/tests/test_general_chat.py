import unittest
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from app.agent.escalation import ContactRecommender
from app.agent.general import GENERAL_TOOL_ID
from app.agent.router import select_tools
from app.integrations.ollama import OllamaClient
from app.schemas import AnswerContext, ToolInput


class GeneralChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_accepts_general_choice(self):
        client = OllamaClient()
        with patch.object(OllamaClient, '_chat', AsyncMock(return_value='{"tool_id":"general","arguments":{}}')) as chat:
            decision = await client.choose_tools('오늘 저녁 메뉴 추천해줘', [])
        self.assertEqual(decision.tool_id, GENERAL_TOOL_ID)
        schema = chat.call_args.kwargs['schema']
        self.assertIn(GENERAL_TOOL_ID, schema['properties']['tool_id']['enum'])

    async def test_unknown_tool_is_still_rejected(self):
        from app.errors import ModelUnavailable
        with patch.object(OllamaClient, '_chat', AsyncMock(return_value='{"tool_id":"nope","arguments":{}}')):
            with self.assertRaises(ModelUnavailable):
                await OllamaClient().choose_tools('질문', [])

    async def test_forced_general_is_allowed(self):
        decision = await select_tools(ToolInput(question='안녕', employee_id='E1', conversation_id=uuid4()), GENERAL_TOOL_ID, None, [], [])
        self.assertEqual(decision.tool_id, GENERAL_TOOL_ID)

    async def test_general_answer_is_plain_text_without_documents(self):
        context = AnswerContext(question='안녕하세요', employee_id='E1')
        with patch.object(OllamaClient, '_chat', AsyncMock(return_value='안녕하세요! 무엇을 도와드릴까요?')) as chat:
            answer = await OllamaClient().generate_general(context)
        self.assertEqual(answer, '안녕하세요! 무엇을 도와드릴까요?')
        self.assertIsNone(chat.call_args.kwargs.get('schema'))
        system = chat.call_args.args[0][0]['content']
        self.assertIn('지어내지', system)

    def test_no_default_contact_when_topic_unmatched(self):
        result = ContactRecommender().recommend('오늘 저녁 메뉴 추천해줘', 'E1', use_default=False)
        self.assertEqual(result.status, 'not_needed')
        self.assertFalse(result.contacts)


if __name__ == '__main__':
    unittest.main()
