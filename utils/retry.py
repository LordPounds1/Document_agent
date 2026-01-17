"""
Retry-декораторы и утилиты для устойчивой работы с внешними сервисами.

Обеспечивает:
- Автоматические повторные попытки при сбоях
- Exponential backoff
- Circuit breaker pattern
- Таймауты
"""

from collections.abc import Callable
import functools
import logging
import random
import time
logger = logging.getLogger(__name__)


class RetryExhausted(Exception):
    """Все попытки исчерпаны."""
    pass


class CircuitOpenError(Exception):
    """Circuit breaker открыт, запросы блокируются."""
    pass


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable | None = None,
):
    """Декоратор для автоматических повторных попыток.

    Args:
        max_attempts: Максимум попыток
        delay: Начальная задержка (секунды)
        backoff: Множитель задержки (exponential backoff)
        max_delay: Максимальная задержка
        jitter: Добавлять случайный разброс к задержке
        exceptions: Какие исключения перехватывать
        on_retry: Callback при повторной попытке (attempt, exception, delay)

    Example:
        @retry(max_attempts=3, delay=1.0, backoff=2.0)
        def fetch_data():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts:
                        logger.error(
                            f"[Retry] {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise RetryExhausted(
                            f"Failed after {max_attempts} attempts: {e}"
                        ) from e

                    # Вычисляем задержку
                    wait_time = min(current_delay, max_delay)
                    if jitter:
                        wait_time = wait_time * (0.5 + random.random())

                    logger.warning(
                        f"[Retry] {func.__name__} attempt {attempt}/{max_attempts} "
                        f"failed: {e}. Retrying in {wait_time:.1f}s..."
                    )

                    # Callback
                    if on_retry:
                        on_retry(attempt, e, wait_time)

                    time.sleep(wait_time)
                    current_delay *= backoff

            raise last_exception

        return wrapper
    return decorator


class CircuitBreaker:
    """Circuit Breaker для защиты от каскадных сбоев.

    States:
    - CLOSED: Нормальная работа
    - OPEN: Запросы блокируются
    - HALF_OPEN: Тестовый запрос для проверки восстановления

    Example:
        circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=30)

        @circuit
        def call_external_service():
            ...
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exceptions: tuple[type[Exception], ...] = (Exception,),
    ):
        """
        Args:
            failure_threshold: Количество ошибок для открытия circuit
            recovery_timeout: Время до перехода в HALF_OPEN (секунды)
            expected_exceptions: Какие исключения считать сбоями
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions

        self._state = self.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._success_count = 0

    @property
    def state(self) -> str:
        """Текущее состояние circuit breaker."""
        if (self._state == self.OPEN and self._last_failure_time and
                (time.time() - self._last_failure_time) >= self.recovery_timeout):
            self._state = self.HALF_OPEN
            logger.info("[CircuitBreaker] Transitioning to HALF_OPEN")
        return self._state

    def _record_success(self):
        """Записать успешный вызов."""
        if self._state == self.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= 2:  # 2 успешных вызова для восстановления
                self._state = self.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info("[CircuitBreaker] Recovered, now CLOSED")
        else:
            self._failure_count = max(0, self._failure_count - 1)

    def _record_failure(self):
        """Записать неуспешный вызов."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._success_count = 0

        if self._failure_count >= self.failure_threshold:
            self._state = self.OPEN
            logger.warning(
                f"[CircuitBreaker] OPEN after {self._failure_count} failures"
            )

    def __call__(self, func: Callable) -> Callable:
        """Декоратор для функции."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Проверяем состояние
            if self.state == self.OPEN:
                raise CircuitOpenError(
                    f"Circuit breaker is OPEN for {func.__name__}"
                )

            try:
                result = func(*args, **kwargs)
                self._record_success()
                return result
            except self.expected_exceptions:
                self._record_failure()
                raise

        return wrapper

    def reset(self):
        """Принудительный сброс circuit breaker."""
        self._state = self.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        logger.info("[CircuitBreaker] Manually reset to CLOSED")


def with_timeout(seconds: float):
    """Декоратор для таймаута операции (только Unix).

    Для Windows используйте threading-based timeout.

    Args:
        seconds: Таймаут в секундах
    """
    import platform
    if platform.system() == "Windows":
        # Windows: возвращаем функцию без изменений
        # Таймауты нужно обрабатывать внутри функций
        def windows_decorator(func):
            return func
        return windows_decorator

    import signal
    def unix_decorator(func: Callable) -> Callable:
        def handler(signum, frame):
            raise TimeoutError(f"{func.__name__} timed out after {seconds}s")

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            old_handler = signal.signal(signal.SIGALRM, handler)
            signal.setitimer(signal.ITIMER_REAL, seconds)
            try:
                return func(*args, **kwargs)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_handler)

        return wrapper
    return unix_decorator


# Готовые circuit breakers для разных сервисов
email_circuit = CircuitBreaker(
    failure_threshold=3,
    recovery_timeout=60.0,
)

llm_circuit = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=120.0,
)
