"""Storage for background monitoring results.

Использует SQLite для хранения:
- Конфигураций мониторинга (email адреса, пароли, настройки)
- Обработанных документов
- Истории проверок
"""

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import sqlite3
logger = logging.getLogger(__name__)

# Путь к базе данных
DB_PATH = os.getenv('MONITOR_DB_PATH', 'data/monitor.db')


@dataclass
class MonitorConfig:
    """Конфигурация мониторинга для email."""
    email_address: str
    password: str  # Зашифрованный пароль
    scan_all: bool = True
    interval_minutes: int = 5
    is_active: bool = True
    created_at: datetime | None = None
    last_check: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'email_address': self.email_address,
            'password': '***',  # Не показываем пароль
            'scan_all': self.scan_all,
            'interval_minutes': self.interval_minutes,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_check': self.last_check.isoformat() if self.last_check else None,
        }


@dataclass
class ProcessedDocument:
    """Обработанный документ."""
    email_id: str
    email_address: str
    email_from: str
    email_subject: str
    email_date: datetime | None
    document_type: str
    summary: str
    parties: str
    amount: str
    responsible: str
    source: str
    processed_at: datetime | None
    id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            'id': self.id,
            'email_id': self.email_id,
            'email_address': self.email_address,
            'email_from': self.email_from,
            'email_subject': self.email_subject,
            'email_date': self.email_date.isoformat() if self.email_date else None,
            'document_type': self.document_type,
            'summary': self.summary,
            'parties': self.parties,
            'amount': self.amount,
            'responsible': self.responsible,
            'source': self.source,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
        }


class MonitorStorage:
    """Хранилище для фонового мониторинга."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or DB_PATH
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self):
        """Создаёт директорию для базы данных."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _get_connection(self):
        """Context manager для соединения с БД."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Инициализация таблиц."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Таблица конфигураций мониторинга
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monitor_configs (
                    email_address TEXT PRIMARY KEY,
                    password_encrypted TEXT NOT NULL,
                    scan_all INTEGER DEFAULT 1,
                    interval_minutes INTEGER DEFAULT 5,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT,
                    last_check TEXT
                )
            ''')

            # Таблица обработанных документов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id TEXT NOT NULL,
                    email_address TEXT NOT NULL,
                    email_from TEXT,
                    email_subject TEXT,
                    email_date TEXT,
                    document_type TEXT,
                    summary TEXT,
                    parties TEXT,
                    amount TEXT,
                    responsible TEXT,
                    source TEXT,
                    processed_at TEXT,
                    UNIQUE(email_id, email_address)
                )
            ''')

            # Индексы
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_docs_email
                ON processed_documents(email_address)
            ''')
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_docs_date
                ON processed_documents(processed_at)
            ''')

            logger.info(f"Database initialized: {self.db_path}")

    # ==========================================
    # Методы для конфигураций мониторинга
    # ==========================================

    def save_config(self, config: MonitorConfig) -> bool:
        """Сохранение конфигурации мониторинга."""
        from utils.security import encrypt_password
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Шифруем пароль
            encrypted_password = encrypt_password(config.password)

            cursor.execute('''
                INSERT OR REPLACE INTO monitor_configs
                (email_address, password_encrypted, scan_all, interval_minutes,
                 is_active, created_at, last_check)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                config.email_address,
                encrypted_password,
                1 if config.scan_all else 0,
                config.interval_minutes,
                1 if config.is_active else 0,
                config.created_at.isoformat() if config.created_at else datetime.now().isoformat(),
                config.last_check.isoformat() if config.last_check else None
            ))

            logger.info(f"Saved config for: {config.email_address}")
            return True

    def get_config(self, email_address: str) -> MonitorConfig | None:
        """Получение конфигурации по email."""
        from utils.security import decrypt_password
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM monitor_configs WHERE email_address = ?',
                (email_address,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            return MonitorConfig(
                email_address=row['email_address'],
                password=decrypt_password(row['password_encrypted']),
                scan_all=bool(row['scan_all']),
                interval_minutes=row['interval_minutes'],
                is_active=bool(row['is_active']),
                created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                last_check=datetime.fromisoformat(row['last_check']) if row['last_check'] else None
            )

    def get_all_active_configs(self) -> list[MonitorConfig]:
        """Получение всех активных конфигураций."""
        from utils.security import decrypt_password
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM monitor_configs WHERE is_active = 1'
            )
            rows = cursor.fetchall()

            configs = []
            for row in rows:
                try:
                    configs.append(MonitorConfig(
                        email_address=row['email_address'],
                        password=decrypt_password(row['password_encrypted']),
                        scan_all=bool(row['scan_all']),
                        interval_minutes=row['interval_minutes'],
                        is_active=True,
                        created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                        last_check=datetime.fromisoformat(row['last_check']) if row['last_check'] else None
                    ))
                except Exception as e:
                    logger.error(f"Failed to load config for {row['email_address']}: {e}")

            return configs

    def deactivate_config(self, email_address: str) -> bool:
        """Деактивация мониторинга."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE monitor_configs SET is_active = 0 WHERE email_address = ?',
                (email_address,)
            )
            logger.info(f"Deactivated monitoring for: {email_address}")
            return cursor.rowcount > 0

    def delete_config(self, email_address: str) -> bool:
        """Удаление конфигурации."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM monitor_configs WHERE email_address = ?',
                (email_address,)
            )
            logger.info(f"Deleted config for: {email_address}")
            return bool(cursor.rowcount and cursor.rowcount > 0)

    def update_last_check(self, email_address: str) -> bool:
        """Обновление времени последней проверки."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE monitor_configs SET last_check = ? WHERE email_address = ?',
                (datetime.now().isoformat(), email_address)
            )
            return bool(cursor.rowcount and cursor.rowcount > 0)

    # ==========================================
    # Методы для документов
    # ==========================================

    def save_document(self, doc: ProcessedDocument) -> int:
        """Сохранение обработанного документа."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO processed_documents
                (email_id, email_address, email_from, email_subject, email_date,
                 document_type, summary, parties, amount, responsible, source, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                doc.email_id,
                doc.email_address,
                doc.email_from,
                doc.email_subject,
                doc.email_date.isoformat() if doc.email_date else None,
                doc.document_type,
                doc.summary,
                doc.parties,
                doc.amount,
                doc.responsible,
                doc.source,
                doc.processed_at.isoformat() if doc.processed_at else datetime.now().isoformat()
            ))

            return cursor.lastrowid

    def get_documents(
        self,
        email_address: str | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[ProcessedDocument]:
        """Получение обработанных документов."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if email_address:
                cursor.execute('''
                    SELECT * FROM processed_documents
                    WHERE email_address = ?
                    ORDER BY processed_at DESC
                    LIMIT ? OFFSET ?
                ''', (email_address, limit, offset))
            else:
                cursor.execute('''
                    SELECT * FROM processed_documents
                    ORDER BY processed_at DESC
                    LIMIT ? OFFSET ?
                ''', (limit, offset))

            rows = cursor.fetchall()

            docs = []
            for row in rows:
                docs.append(ProcessedDocument(
                    id=row['id'],
                    email_id=row['email_id'],
                    email_address=row['email_address'],
                    email_from=row['email_from'],
                    email_subject=row['email_subject'],
                    email_date=datetime.fromisoformat(row['email_date']) if row['email_date'] else None,
                    document_type=row['document_type'],
                    summary=row['summary'],
                    parties=row['parties'],
                    amount=row['amount'],
                    responsible=row['responsible'],
                    source=row['source'],
                    processed_at=datetime.fromisoformat(row['processed_at']) if row['processed_at'] else None
                ))

            return docs

    def get_processed_email_ids(self, email_address: str) -> set[str]:
        """Получение ID уже обработанных email."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT email_id FROM processed_documents WHERE email_address = ?',
                (email_address,)
            )
            return {row['email_id'] for row in cursor.fetchall()}

    def get_documents_count(self, email_address: str = None) -> int:
        """Получение количества документов."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if email_address:
                cursor.execute(
                    'SELECT COUNT(*) as cnt FROM processed_documents WHERE email_address = ?',
                    (email_address,)
                )
            else:
                cursor.execute('SELECT COUNT(*) as cnt FROM processed_documents')

            return cursor.fetchone()['cnt']

    def cleanup_old_documents(self, days: int = 30) -> int:
        """Удаление документов старше N дней."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM processed_documents WHERE processed_at < ?',
                (cutoff,)
            )
            deleted = cursor.rowcount or 0
            logger.info(f"Cleaned up {deleted} old documents")
            return int(deleted)

    # ==========================================
    # Статистика
    # ==========================================

    def get_stats(self) -> dict[str, Any]:
        """Получение общей статистики."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Количество активных мониторов
            cursor.execute('SELECT COUNT(*) as cnt FROM monitor_configs WHERE is_active = 1')
            active_monitors = cursor.fetchone()['cnt']

            # Количество документов
            cursor.execute('SELECT COUNT(*) as cnt FROM processed_documents')
            total_documents = cursor.fetchone()['cnt']

            # Документы за последние 24 часа
            day_ago = (datetime.now() - timedelta(days=1)).isoformat()
            cursor.execute(
                'SELECT COUNT(*) as cnt FROM processed_documents WHERE processed_at > ?',
                (day_ago,)
            )
            documents_24h = cursor.fetchone()['cnt']

            return {
                'active_monitors': active_monitors,
                'total_documents': total_documents,
                'documents_24h': documents_24h
            }
