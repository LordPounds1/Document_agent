"""
Метрики и структурированное логирование для observability.

Обеспечивает:
- Счётчики обработанных документов
- Время выполнения операций
- Структурированные логи в JSON
- Экспорт метрик
"""

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Metric:
    """Отдельная метрика."""
    name: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
        }


class MetricsCollector:
    """Коллектор метрик приложения."""

    def __init__(self):
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._lock = Lock()
        self._start_time = time.time()

    # ============ Counters ============

    def increment(self, name: str, value: float = 1.0, labels: Dict | None = None):
        """Увеличить счётчик."""
        key = self._make_key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    def get_counter(self, name: str, labels: Dict | None = None) -> float:
        """Получить значение счётчика."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    # ============ Gauges ============

    def set_gauge(self, name: str, value: float, labels: Dict | None = None):
        """Установить значение gauge."""
        key = self._make_key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def get_gauge(self, name: str, labels: Dict | None = None) -> float:
        """Получить значение gauge."""
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0)

    # ============ Histograms ============

    def observe(self, name: str, value: float, labels: Dict | None = None):
        """Записать значение в гистограмму."""
        key = self._make_key(name, labels)
        with self._lock:
            if key not in self._histograms:
                self._histograms[key] = []
            self._histograms[key].append(value)
            # Ограничиваем размер
            if len(self._histograms[key]) > 10000:
                self._histograms[key] = self._histograms[key][-5000:]

    def get_histogram_stats(self, name: str, labels: Dict | None = None) -> Dict:
        """Получить статистику гистограммы."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])

        if not values:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}

        sorted_values = sorted(values)
        count = len(sorted_values)

        return {
            "count": count,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "avg": sum(sorted_values) / count,
            "p50": sorted_values[int(count * 0.5)],
            "p95": sorted_values[int(count * 0.95)] if count > 20 else sorted_values[-1],
            "p99": sorted_values[int(count * 0.99)] if count > 100 else sorted_values[-1],
        }

    # ============ Timing ============

    @contextmanager
    def timer(self, name: str, labels: Dict | None = None):
        """Context manager для измерения времени."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            self.observe(f"{name}_duration_seconds", duration, labels)
            self.increment(f"{name}_total", 1, labels)

    def timed(self, name: str, labels: Dict | None = None):
        """Декоратор для измерения времени выполнения функции."""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self.timer(name, labels):
                    return func(*args, **kwargs)
            return wrapper
        return decorator

    # ============ Export ============

    def _make_key(self, name: str, labels: Dict | None) -> str:
        """Создать уникальный ключ для метрики."""
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name

    def get_all_metrics(self) -> dict[str, Any]:
        """Получить все метрики."""
        uptime = time.time() - self._start_time

        return {
            "uptime_seconds": uptime,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {
                name: self.get_histogram_stats(name.split("{")[0])
                for name in self._histograms
            },
            "timestamp": datetime.now().isoformat(),
        }

    def export_json(self, filepath: Path | None = None) -> str:
        """Экспорт метрик в JSON."""
        metrics = self.get_all_metrics()
        json_str = json.dumps(metrics, indent=2, ensure_ascii=False)

        if filepath:
            filepath.write_text(json_str, encoding="utf-8")

        return json_str

    def reset(self):
        """Сброс всех метрик."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._start_time = time.time()


# Глобальный экземпляр
metrics = MetricsCollector()


# ============ Structured Logging ============

class StructuredLogger:
    """Структурированное логирование в JSON формате."""

    def __init__(self, name: str, log_file: Path | None = None):
        self.name = name
        self.log_file = log_file
        self._logger = logging.getLogger(name)

    def _log(self, level: str, message: str, **context):
        """Базовый метод логирования."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "logger": self.name,
            "message": message,
            **context
        }

        # Убираем None значения
        log_entry = {k: v for k, v in log_entry.items() if v is not None}

        json_line = json.dumps(log_entry, ensure_ascii=False, default=str)

        # В файл
        if self.log_file:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json_line + "\n")

        # В стандартный logger
        log_func = getattr(self._logger, level.lower(), self._logger.info)
        log_func(json_line)

    def info(self, message: str, **context):
        self._log("INFO", message, **context)

    def warning(self, message: str, **context):
        self._log("WARNING", message, **context)

    def error(self, message: str, **context):
        self._log("ERROR", message, **context)

    def debug(self, message: str, **context):
        self._log("DEBUG", message, **context)


# ============ Предопределённые метрики ============

def record_email_processed(success: bool, email_from: str = "", has_contract: bool = False):
    """Записать обработку email."""
    metrics.increment("emails_processed_total", labels={"success": str(success).lower()})
    if has_contract:
        metrics.increment("contracts_found_total")


def record_llm_inference(duration: float, tokens: int = 0, success: bool = True):
    """Записать LLM inference."""
    metrics.observe("llm_inference_duration_seconds", duration)
    metrics.increment("llm_inferences_total", labels={"success": str(success).lower()})
    if tokens:
        metrics.increment("llm_tokens_total", tokens)


def record_document_extraction(doc_type: str, success: bool, duration: float):
    """Записать извлечение данных из документа."""
    metrics.increment(
        "documents_extracted_total",
        labels={"type": doc_type, "success": str(success).lower()}
    )
    metrics.observe("document_extraction_duration_seconds", duration)


def get_dashboard_stats() -> dict[str, Any]:
    """Получить статистику для дашборда."""
    return {
        "emails_processed": metrics.get_counter("emails_processed_total", {"success": "true"}),
        "emails_failed": metrics.get_counter("emails_processed_total", {"success": "false"}),
        "contracts_found": metrics.get_counter("contracts_found_total"),
        "llm_inferences": metrics.get_counter("llm_inferences_total", {"success": "true"}),
        "llm_latency": metrics.get_histogram_stats("llm_inference_duration_seconds"),
        "uptime_seconds": time.time() - metrics._start_time,
    }
