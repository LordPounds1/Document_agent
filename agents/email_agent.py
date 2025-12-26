import email
import imaplib
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from typing import List, Dict, Optional
import logging
from config import Config

logger = logging.getLogger(__name__)

class EmailAgent:
    """Агент для работы с почтой"""
    
    def __init__(self):
        self.imap = None
        self.smtp = None
        self.connected_imap = False
        self.connected_smtp = False
    
    def connect_imap(self) -> bool:
        """Подключение к IMAP серверу"""
        try:
            if not Config.EMAIL_ADDRESS or not Config.EMAIL_PASSWORD:
                logger.error("EMAIL_ADDRESS или EMAIL_PASSWORD не настроены")
                return False
            
            if Config.USE_SSL:
                self.imap = imaplib.IMAP4_SSL(Config.IMAP_SERVER, Config.IMAP_PORT, timeout=30)
            else:
                self.imap = imaplib.IMAP4(Config.IMAP_SERVER, Config.IMAP_PORT, timeout=30)
                self.imap.starttls()
            
            try:
                self.imap.login(Config.EMAIL_ADDRESS, Config.EMAIL_PASSWORD)
            except imaplib.IMAP4.error as login_error:
                if '@' in Config.EMAIL_ADDRESS and 'yandex' in Config.EMAIL_ADDRESS.lower():
                    username = Config.EMAIL_ADDRESS.split('@')[0]
                    logger.info(f"Попытка подключения с именем пользователя: {username}")
                    try:
                        self.imap.login(username, Config.EMAIL_PASSWORD)
                    except:
                        raise login_error
                else:
                    raise login_error
            
            self.connected_imap = True
            logger.info(f"Успешное подключение к IMAP: {Config.IMAP_SERVER}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка подключения к IMAP: {e}")
            return False
    
    def connect(self) -> bool:
        return self.connect_imap()
    
    def disconnect(self):
        if self.connected_imap and self.imap:
            try:
                self.imap.logout()
                self.connected_imap = False
            except:
                pass

    def mark_as_read(self, email_id: str):
        if self.connected_imap and self.imap:
            try:
                self.imap.store(email_id, '+FLAGS', '\\Seen')
            except:
                pass
    
    def fetch_unread_emails(self) -> List[Dict]:
        """Получение непрочитанных писем"""
        if not self.connected_imap:
            if not self.connect_imap():
                return []
        
        emails = []
        try:
            self.imap.select("INBOX")
            status, messages = self.imap.search(None, 'UNSEEN')
            
            if status != 'OK':
                return emails
            
            for num in messages[0].split():
                try:
                    status, data = self.imap.fetch(num, '(RFC822)')
                    if status != 'OK':
                        continue
                    
                    email_body = data[0][1]
                    email_message = email.message_from_bytes(email_body)
                    
                    subject = self._decode_header(email_message['Subject'])
                    from_ = self._decode_header(email_message['From'])
                    text_content = self._extract_text(email_message)
                    attachments = self._extract_attachments(email_message)
                    
                    emails.append({
                        'id': num.decode(),
                        'subject': subject,
                        'from': from_,
                        'body': text_content,
                        'attachments': attachments, # Теперь здесь просто данные, без текста
                        'date': email_message['Date'],
                        'raw': email_message
                    })
                    
                    logger.info(f"Найдено письмо: {subject} от {from_}")
                    
                except Exception as e:
                    logger.error(f"Ошибка обработки письма {num}: {e}")
        
        except Exception as e:
            logger.error(f"Ошибка получения писем: {e}")
        
        return emails
    
    def _decode_header(self, header: str) -> str:
        if header is None:
            return ""
        decoded_parts = decode_header(header)
        result = []
        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                if encoding:
                    try:
                        result.append(part.decode(encoding))
                    except:
                        result.append(part.decode('utf-8', errors='ignore'))
                else:
                    result.append(part.decode('utf-8', errors='ignore'))
            else:
                result.append(part)
        return ' '.join(result)
    
    def _extract_text(self, email_message) -> str:
        text_content = ""
        if email_message.is_multipart():
            for part in email_message.walk():
                if "attachment" in str(part.get("Content-Disposition")):
                    continue
                if part.get_content_type() == "text/plain":
                    try:
                        text_content += part.get_payload(decode=True).decode()
                    except:
                        pass
        else:
            try:
                text_content = email_message.get_payload(decode=True).decode()
            except:
                pass
        return text_content.strip()
    
    def _extract_attachments(self, email_message) -> List[Dict]:
        """Извлечение вложений (только бинарные данные)"""
        attachments = []
        if email_message.is_multipart():
            for part in email_message.walk():
                if "attachment" in str(part.get("Content-Disposition")):
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_header(filename)
                        file_data = part.get_payload(decode=True)
                        
                        attachments.append({
                            'filename': filename,
                            'data': file_data,
                            'content_type': part.get_content_type()
                        })
        return attachments