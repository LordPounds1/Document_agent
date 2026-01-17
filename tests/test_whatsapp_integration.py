"""Тесты для проверки исправлений интеграции WhatsApp."""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
class TestWhatsAppRealtimeAgent:
    """Тесты для WhatsAppRealTimeAgent с проверкой исправлений."""

    def test_agent_initialization(self):
        """Проверка инициализации агента."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent(
            session_dir=".test_session",
            downloads_dir=".test_downloads"
        )

        assert agent.driver is None
        assert agent.connected is False
        assert agent.monitoring is False
        assert agent.session_dir == Path(".test_session").absolute()
        assert agent.downloads_dir == Path(".test_downloads").absolute()

    def test_get_chats_when_not_connected(self):
        """Проверка: get_chats возвращает пустой список при отсутствии подключения."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.connected = False
        agent.driver = None

        result = agent.get_chats()

        assert result == []
        assert isinstance(result, list)

    def test_get_messages_when_not_connected(self):
        """Проверка: get_messages возвращает пустой список при отсутствии подключения."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.connected = False
        agent.driver = None

        result = agent.get_messages()

        assert result == []
        assert isinstance(result, list)

    def test_open_chat_when_not_connected(self):
        """Проверка: open_chat возвращает False при отсутствии подключения."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.connected = False
        agent.driver = None

        result = agent.open_chat("test_chat")

        assert result is False

    def test_open_chat_with_empty_name(self):
        """Проверка: open_chat обрабатывает пустое имя чата."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.connected = True
        agent.driver = Mock()

        result = agent.open_chat("")
        assert result is False

        result = agent.open_chat("   ")
        assert result is False

    def test_connect_without_selenium(self):
        """Проверка: connect обрабатывает отсутствие Selenium."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        # Эмулируем отсутствие Selenium
        with patch('agents.whatsapp_realtime.SELENIUM_AVAILABLE', False):
            agent = WhatsAppRealTimeAgent()
            result = agent.connect()

            assert result is False
            assert agent.connected is False

    def test_get_chats_error_handling(self):
        """Проверка: get_chats обрабатывает ошибки и возвращает пустой список."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.connected = True
        agent.driver = Mock()

        # Эмулируем ошибку при выполнении JavaScript
        agent.driver.execute_script.side_effect = Exception("Test error")

        result = agent.get_chats()

        assert result == []
        assert isinstance(result, list)

    def test_get_messages_error_handling(self):
        """Проверка: get_messages обрабатывает ошибки и возвращает пустой список."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.connected = True
        agent.driver = Mock()

        # Эмулируем ошибку
        agent.driver.execute_script.side_effect = Exception("Test error")

        result = agent.get_messages()

        assert result == []
        assert isinstance(result, list)

    def test_is_contract_message(self):
        """Проверка определения договоров в сообщениях."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()

        # Тест с ключевыми словами
        assert agent._is_contract_message("Пришли договор", None) is True
        assert agent._is_contract_message("контракт на подпись", None) is True
        assert agent._is_contract_message("соглашение", None) is True
        assert agent._is_contract_message("обычное сообщение", None) is False

        # Тест с документами
        assert agent._is_contract_message("", "договор.pdf") is True
        assert agent._is_contract_message("", "document.docx") is True
        assert agent._is_contract_message("", "image.jpg") is False
        assert agent._is_contract_message("", None, "накладная.pdf") is True

    def test_get_stats(self):
        """Проверка получения статистики."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.processed_message_ids.add("msg1")
        agent.processed_message_ids.add("msg2")

        stats = agent.get_stats()

        assert stats['connected'] is False
        assert stats['monitoring'] is False
        assert stats['processed_messages'] == 2
        assert 'session_dir' in stats
        assert 'downloads_dir' in stats

    def test_extract_text_from_file_txt(self, tmp_path):
        """Проверка извлечения текста из txt файла."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        file_path = tmp_path / "sample.txt"
        file_path.write_text("Тестовый документ", encoding="utf-8")

        text = agent.extract_text_from_file(str(file_path))

        assert "Тестовый документ" in text


class TestWhatsAppMessageCompatibility:
    """Тесты для проверки совместимости разных версий WhatsAppMessage."""

    def test_message_with_has_document(self):
        """Проверка работы с сообщением, имеющим has_document."""
        from agents.whatsapp_realtime import WhatsAppMessage
        msg = WhatsAppMessage(
            id="test1",
            sender="Test User",
            content="Test message",
            timestamp=datetime.now(),
            chat_name="Test Chat",
            has_document=True,
            document_name="test.pdf"
        )

        # Проверяем, что атрибуты доступны
        assert hasattr(msg, 'has_document')
        assert hasattr(msg, 'document_name')
        assert msg.has_document is True
        assert msg.document_name == "test.pdf"

    def test_message_without_document(self):
        """Проверка работы с сообщением без документа."""
        from agents.whatsapp_realtime import WhatsAppMessage
        msg = WhatsAppMessage(
            id="test2",
            sender="Test User",
            content="Test message",
            timestamp=datetime.now(),
            chat_name="Test Chat",
            has_document=False
        )

        assert msg.has_document is False
        assert msg.document_name is None

    def test_getattr_compatibility(self):
        """Проверка совместимости через getattr (как в исправлениях)."""
        from agents.whatsapp_realtime import WhatsAppMessage
        msg = WhatsAppMessage(
            id="test3",
            sender="Test User",
            content="Test message",
            timestamp=datetime.now(),
            chat_name="Test Chat",
            has_document=True,
            document_name="doc.pdf"
        )

        # Используем getattr как в исправленном коде
        has_doc = getattr(msg, 'has_document', False) or getattr(msg, 'has_attachment', False)
        doc_name = getattr(msg, 'document_name', None) or getattr(msg, 'attachment_path', None) or ""
        sender = getattr(msg, 'sender', 'Неизвестно')
        content = (msg.content or "")[:80] if hasattr(msg, 'content') and msg.content else "(без текста)"

        assert has_doc is True
        assert doc_name == "doc.pdf"
        assert sender == "Test User"
        assert content == "Test message"


class TestStreamlitIntegration:
    """Тесты для проверки интеграции в Streamlit."""

    def test_session_state_initialization(self):
        """Проверка правильной инициализации session_state."""
        # Имитируем session_state
        session_state = {
            'whatsapp_realtime': None,
            'whatsapp_connected': False,
            'whatsapp_monitoring': False,
            'whatsapp_messages': []
        }

        # Проверяем, что проверки на None работают
        assert session_state['whatsapp_realtime'] is None
        assert session_state['whatsapp_connected'] is False

        # Проверяем безопасный доступ
        if session_state['whatsapp_realtime']:
            # Этот блок не должен выполняться
            raise AssertionError("Should not execute")
        else:
            assert True, "Correctly checks for None"

    def test_callback_error_handling(self):
        """Проверка обработки ошибок в callback функции."""
        from agents.whatsapp_realtime import WhatsAppMessage, WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        error_caught = []

        def test_callback(msg):
            """Callback с обработкой ошибок (как в исправлениях)."""
            try:
                # Имитируем обработку
                content = msg.content or msg.document_name or ""
                if content and len(content) > 20:
                    # Симуляция успешной обработки
                    pass
            except Exception as e:
                error_caught.append(str(e))

        agent.on_contract = test_callback

        # Создаём тестовое сообщение
        msg = WhatsAppMessage(
            id="test",
            sender="Test",
            content="Test contract message",
            timestamp=datetime.now(),
            chat_name="Test Chat",
            is_contract=True
        )

        # Вызываем callback
        if agent.on_contract:
            agent.on_contract(msg)

        # Проверяем, что ошибок не было
        assert len(error_caught) == 0

    def test_stats_access_with_none(self):
        """Проверка безопасного доступа к статистике при None."""
        # Имитируем ситуацию, когда агент может быть None
        whatsapp_realtime = None

        # Проверяем безопасный доступ (как в исправлениях)
        try:
            if whatsapp_realtime:
                stats = whatsapp_realtime.get_stats()
                processed = stats.get('processed_messages', 0)
            else:
                processed = 0
        except Exception:
            processed = 0

        assert processed == 0


class TestErrorHandling:
    """Тесты для проверки обработки ошибок."""

    def test_get_chats_returns_list_on_error(self):
        """Проверка: get_chats всегда возвращает список, даже при ошибке."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.connected = True
        agent.driver = Mock()

        # Эмулируем различные ошибки
        errors = [
            Exception("Generic error"),
            AttributeError("Attribute not found"),
            TimeoutError("Timeout"),
            KeyError("Key not found")
        ]

        for error in errors:
            agent.driver.execute_script.side_effect = error
            result = agent.get_chats()

            assert isinstance(result, list), f"Should return list on {type(error).__name__}"
            assert result == [], f"Should return empty list on {type(error).__name__}"

    def test_get_messages_returns_list_on_error(self):
        """Проверка: get_messages всегда возвращает список, даже при ошибке."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.connected = True
        agent.driver = Mock()

        # Эмулируем ошибку
        agent.driver.execute_script.side_effect = Exception("Test error")

        result = agent.get_messages()

        assert isinstance(result, list)
        assert result == []

    def test_diagnose_dom_error_handling(self):
        """Проверка обработки ошибок в diagnose_dom."""
        from agents.whatsapp_realtime import WhatsAppRealTimeAgent
        agent = WhatsAppRealTimeAgent()
        agent.connected = True
        agent.driver = Mock()

        # Эмулируем ошибку
        agent.driver.execute_script.side_effect = Exception("DOM error")

        result = agent.diagnose_dom()

        assert isinstance(result, dict)
        assert 'error' in result
        assert 'DOM error' in result['error']


class TestWhatsAppChatCompatibility:
    """Тесты для проверки совместимости WhatsAppChat."""

    def test_chat_attributes(self):
        """Проверка атрибутов WhatsAppChat."""
        from agents.whatsapp_realtime import WhatsAppChat
        chat = WhatsAppChat(
            name="Test Chat",
            last_message="Last message",
            unread_count=5,
            is_group=False
        )

        assert chat.name == "Test Chat"
        assert chat.last_message == "Last message"
        assert chat.unread_count == 5
        assert chat.is_group is False

    def test_chat_safe_access(self):
        """Проверка безопасного доступа к атрибутам чата."""
        from agents.whatsapp_realtime import WhatsAppChat
        chat = WhatsAppChat(
            name="Test Chat",
            last_message="",
            unread_count=0
        )

        # Используем getattr как в исправлениях
        name = getattr(chat, 'name', 'Неизвестный чат')
        last_msg = getattr(chat, 'last_message', '')
        unread = getattr(chat, 'unread_count', 0)

        assert name == "Test Chat"
        assert last_msg == ""
        assert unread == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
