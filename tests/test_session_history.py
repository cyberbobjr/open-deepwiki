from __future__ import annotations

import unittest

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from router.routes_ask import _extract_history_messages, _message_role_and_content


class TestSessionHistoryExtraction(unittest.TestCase):
    def test_extracts_messages_from_primary_key(self) -> None:
        msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]
        out = _extract_history_messages({"messages": msgs, "other": 123})
        self.assertEqual(out, msgs)

    def test_extracts_messages_from_fallback_keys(self) -> None:
        msgs = [HumanMessage(content="hi")]
        out = _extract_history_messages({"chat_history": msgs})
        self.assertEqual(out, msgs)

    def test_role_and_content_human(self) -> None:
        role, content = _message_role_and_content(HumanMessage(content="Q"))
        self.assertEqual(role, "user")
        self.assertEqual(content, "Q")

    def test_role_and_content_ai(self) -> None:
        role, content = _message_role_and_content(AIMessage(content="A"))
        self.assertEqual(role, "assistant")
        self.assertEqual(content, "A")

    def test_role_and_content_system(self) -> None:
        role, content = _message_role_and_content(SystemMessage(content="S"))
        self.assertEqual(role, "system")
        self.assertEqual(content, "S")

    def test_role_and_content_dict(self) -> None:
        role, content = _message_role_and_content({"role": "assistant", "content": "hello"})
        self.assertEqual(role, "assistant")
        self.assertEqual(content, "hello")


if __name__ == "__main__":
    unittest.main()
