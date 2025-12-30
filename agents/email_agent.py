"""Упрощённый агент для работы с почтой"""

import email
import imaplib
import io
from email.header import decode_header
from typing import List, Dict, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailAgent:
    """Агент для работы с почтой (IMAP)"""
    
    # Настройки для разных почтовых провайдеров
    PROVIDERS = {
        'gmail.com': {'imap': 'imap.gmail.com', 'port': 993},
        'googlemail.com': {'imap': 'imap.gmail.com', 'port': 993},
        'yandex.ru': {'imap': 'imap.yandex.ru', 'port': 993},
        'yandex.com': {'imap': 'imap.yandex.com', 'port': 993},
        'ya.ru': {'imap': 'imap.yandex.ru', 'port': 993},
        'mail.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'inbox.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'list.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'bk.ru': {'imap': 'imap.mail.ru', 'port': 993},
        'outlook.com': {'imap': 'outlook.office365.com', 'port': 993},
        'hotmail.com': {'imap': 'outlook.office365.com', 'port': 993},
    }
    
    def __init__(self):
        self.imap = None
        self.connected = False
        self.email_address = None
        self.provider_settings = None
    
    def _detect_provider(self, email_address: str) -> Dict:
        """Определение настроек по email адресу"""
        domain = email_address.split('@')[-1].lower()
        
        if domain in self.PROVIDERS:
            return self.PROVIDERS[domain]
        
        # Default - пробуем imap.domain
        return {'imap': f'imap.{domain}', 'port': 993}
    
    def connect(self, email_address: str, password: str) -> bool:
        """Подключение к почтовому серверу
        
        Args:
            email_address: Email адрес
            password: Пароль (для Gmail - App Password)
            
        Returns:
            True если подключение успешно
        """
        try:
            self.email_address = email_address
            self.provider_settings = self._detect_provider(email_address)
            
            server = self.provider_settings['imap']
            port = self.provider_settings['port']
            
            logger.info(f"Подключение к {server}:{port}...")
            
            self.imap = imaplib.IMAP4_SSL(server, port)
            self.imap.login(email_address, password)
            self.connected = True
            
            logger.info(f"✅ Успешное подключение к {server}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Отключение от сервера"""
        if self.connected and self.imap:
            try:
                self.imap.logout()
            except:
                pass
            self.connected = False
            logger.info("Отключено от почтового сервера")
    
    def fetch_emails(self, folder: str = "INBOX", 
                     unread_only: bool = True,
                     limit: int = 50) -> List[Dict]:
        """Получение писем из папки
        
        Args:
            folder: Папка (INBOX, Sent, и т.д.)
            unread_only: Только непрочитанные
            limit: Максимум писем
            
        Returns:
            Список писем
        """
        if not self.connected:
            logger.warning("Нет подключения к почте")
            return []
        
        emails = []
        try:
            # Выбираем папку
            status, _ = self.imap.select(folder)
            if status != 'OK':
                logger.error(f"Не удалось открыть папку {folder}")
                return []
            
            # Поиск писем
            search_criteria = 'UNSEEN' if unread_only else 'ALL'
            status, messages = self.imap.search(None, search_criteria)
            
            if status != 'OK':
                return []
            
            message_nums = messages[0].split()
            # Берём последние limit писем
            message_nums = message_nums[-limit:]
            
            logger.info(f"Найдено {len(message_nums)} писем")
            
            for num in message_nums:
                try:
                    email_data = self._fetch_email(num)
                    if email_data:
                        emails.append(email_data)
                except Exception as e:
                    logger.warning(f"Ошибка обработки письма {num}: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка получения писем: {e}")
        
        return emails
    
    def _fetch_email(self, num: bytes) -> Optional[Dict]:
        """Получение одного письма"""
        status, data = self.imap.fetch(num, '(RFC822)')
        
        if status != 'OK':
            return None
        
        email_body = data[0][1]
        email_message = email.message_from_bytes(email_body)
        
        # Декодируем заголовки
        subject = self._decode_header(email_message['Subject'])
        from_addr = self._decode_header(email_message['From'])
        date_str = email_message['Date']
        message_id = email_message['Message-ID']
        
        # Парсим дату
        try:
            from email.utils import parsedate_to_datetime
            date = parsedate_to_datetime(date_str)
        except:
            date = datetime.now()
        
        # Извлекаем текст
        body = self._extract_body(email_message)
        
        # Извлекаем вложения
        attachments = self._extract_attachments(email_message)
        
        return {
            'id': num.decode(),
            'message_id': message_id,
            'subject': subject,
            'from': from_addr,
            'date': date,
            'date_str': date_str,
            'body': body,
            'attachments': attachments,
            'has_attachments': len(attachments) > 0
        }
    
    def _decode_header(self, header: str) -> str:
        """Декодирование заголовка"""
        if header is None:
            return ""
        
        decoded_parts = decode_header(header)
        result = []
        
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                try:
                    result.append(part.decode(encoding or 'utf-8', errors='replace'))
                except:
                    result.append(part.decode('utf-8', errors='replace'))
            else:
                result.append(part)
        
        return ''.join(result)
    
    def _extract_body(self, msg) -> str:
        """Извлечение текста письма"""
        body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        charset = part.get_content_charset() or 'utf-8'
                        body = part.get_payload(decode=True).decode(charset, errors='replace')
                        break
                    except:
                        pass
        else:
            try:
                charset = msg.get_content_charset() or 'utf-8'
                body = msg.get_payload(decode=True).decode(charset, errors='replace')
            except:
                body = str(msg.get_payload())
        
        return body
    
    def _extract_attachments(self, msg) -> List[Dict]:
        """Извлечение вложений"""
        attachments = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition"))
                
                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_header(filename)
                        content = part.get_payload(decode=True)
                        
                        attachments.append({
                            'filename': filename,
                            'content': content,
                            'size': len(content) if content else 0,
                            'content_type': part.get_content_type()
                        })
        
        return attachments
    
    def mark_as_read(self, email_id: str):
        """Пометить письмо как прочитанное"""
        if self.connected:
            try:
                self.imap.store(email_id.encode(), '+FLAGS', '\\Seen')
            except:
                pass
    
    def get_attachment_text(self, attachment: Dict) -> str:
        """Извлечение текста из вложения"""
        filename = attachment.get('filename', '').lower()
        content = attachment.get('content', b'')
        
        if not content:
            return ""
        
        try:
            # DOCX файлы
            if filename.endswith('.docx'):
                import docx2txt
                return docx2txt.process(io.BytesIO(content))
            
            # PDF файлы
            elif filename.endswith('.pdf'):
                try:
                    import PyPDF2
                    reader = PyPDF2.PdfReader(io.BytesIO(content))
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    return text
                except ImportError:
                    logger.warning("PyPDF2 not installed for PDF processing")
                    return ""
            
            # TXT файлы
            elif filename.endswith('.txt'):
                return content.decode('utf-8', errors='replace')
            
        except Exception as e:
            logger.error(f"Ошибка извлечения текста из {filename}: {e}")
        
        return ""
