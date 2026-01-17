"""Tests for agents/email_agent.py."""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestEmailAgent:
    """Тесты для класса EmailAgent."""

    def test_agent_initialization(self):
        """Проверка инициализации агента."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        assert agent.imap is None
        assert agent.connected is False
        assert agent.email_address is None

    def test_providers_exist(self):
        """Проверка наличия провайдеров."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        assert len(agent.PROVIDERS) > 0
        assert 'gmail.com' in agent.PROVIDERS
        assert 'yandex.ru' in agent.PROVIDERS

    def test_detect_provider_gmail(self):
        """Проверка определения Gmail."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        settings = agent._detect_provider("test@gmail.com")
        assert settings['imap'] == 'imap.gmail.com'

    def test_detect_provider_yandex(self):
        """Проверка определения Yandex."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        settings = agent._detect_provider("test@yandex.ru")
        assert settings['imap'] == 'imap.yandex.ru'

    def test_detect_provider_mailru(self):
        """Проверка определения Mail.ru."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        settings = agent._detect_provider("test@mail.ru")
        assert settings['imap'] == 'imap.mail.ru'

    def test_detect_provider_unknown(self):
        """Проверка определения неизвестного провайдера."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        settings = agent._detect_provider("test@custom-domain.com")
        assert settings['imap'] == 'imap.custom-domain.com'
        assert settings['port'] == 993

    def test_decode_header_plain_text(self):
        """Проверка декодирования простого заголовка."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        result = agent._decode_header("Simple Subject")
        assert result == "Simple Subject"

    def test_decode_header_none(self):
        """Проверка декодирования None."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        result = agent._decode_header(None)
        assert result == ""

    def test_disconnect_when_not_connected(self):
        """Проверка отключения когда не подключен."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        # Не должно вызывать ошибку
        agent.disconnect()
        assert agent.connected is False

    def test_fetch_emails_when_not_connected(self):
        """Проверка получения писем без подключения."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        emails = agent.fetch_emails()
        assert emails == []

    @patch('agents.email_agent.imaplib.IMAP4_SSL')
    def test_connect_success(self, mock_imap):
        """Проверка успешного подключения."""
        from agents.email_agent import EmailAgent

        # Настройка мока
        mock_instance = MagicMock()
        mock_imap.return_value = mock_instance

        agent = EmailAgent()
        result = agent.connect("test@gmail.com", "password123")

        assert result is True
        assert agent.connected is True
        mock_instance.login.assert_called_once_with("test@gmail.com", "password123")

    @patch('agents.email_agent.imaplib.IMAP4_SSL')
    def test_connect_failure(self, mock_imap):
        """Проверка неудачного подключения."""
        from agents.email_agent import EmailAgent

        # Настройка мока для ошибки
        mock_imap.side_effect = Exception("Connection failed")

        agent = EmailAgent()
        result = agent.connect("test@gmail.com", "wrong_password")

        assert result is False
        assert agent.connected is False

    def test_get_attachment_text_txt(self):
        """Проверка извлечения текста из TXT."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        attachment = {
            'filename': 'test.txt',
            'content': b'Hello World'
        }

        result = agent.get_attachment_text(attachment)
        assert result == 'Hello World'

    def test_get_attachment_text_empty(self):
        """Проверка обработки пустого вложения."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        attachment = {
            'filename': 'test.txt',
            'content': b''
        }

        result = agent.get_attachment_text(attachment)
        assert result == ""

    def test_get_attachment_text_unsupported(self):
        """Проверка обработки неподдерживаемого формата."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        attachment = {
            'filename': 'test.jpg',
            'content': b'binary data'
        }

        result = agent.get_attachment_text(attachment)
        assert result == ""

    def test_mark_as_read_when_not_connected(self):
        """Проверка пометки письма без подключения."""
        from agents.email_agent import EmailAgent
        agent = EmailAgent()

        # Не должно вызывать ошибку
        agent.mark_as_read("123")
