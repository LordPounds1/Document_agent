"""
Тесты для модуля retry и circuit breaker.
"""

import time
import pytest
from utils.retry import (
    CircuitBreaker,
    CircuitOpenError,
    RetryExhausted,
    retry,
)


class TestRetryDecorator:
    """Тесты декоратора retry."""

    def test_success_on_first_try(self):
        """Успех с первой попытки."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_function()
        assert result == "success"
        assert call_count == 1

    def test_success_after_retry(self):
        """Успех после повторной попытки."""
        call_count = 0

        @retry(max_attempts=3, delay=0.01)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        result = flaky_function()
        assert result == "success"
        assert call_count == 3

    def test_exhausted_retries(self):
        """Исчерпание попыток."""
        @retry(max_attempts=3, delay=0.01)
        def always_fails():
            raise ValueError("Always fails")

        with pytest.raises(RetryExhausted):
            always_fails()

    def test_specific_exceptions(self):
        """Перехват только указанных исключений."""
        @retry(max_attempts=3, delay=0.01, exceptions=(ConnectionError,))
        def raises_value_error():
            raise ValueError("Not retryable")

        # ValueError не перехватывается - должен пробросить сразу
        with pytest.raises(ValueError):
            raises_value_error()

    def test_on_retry_callback(self):
        """Callback при повторных попытках."""
        attempts = []

        def on_retry(attempt, exception, delay):
            attempts.append(attempt)

        @retry(max_attempts=3, delay=0.01, on_retry=on_retry)
        def flaky():
            if len(attempts) < 2:
                raise RuntimeError("Fail")
            return "ok"

        result = flaky()
        assert result == "ok"
        assert attempts == [1, 2]


class TestCircuitBreaker:
    """Тесты Circuit Breaker."""

    def test_closed_state_normal_operation(self):
        """Нормальная работа в закрытом состоянии."""
        circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=1)

        @circuit
        def successful():
            return "success"

        assert successful() == "success"
        assert circuit.state == CircuitBreaker.CLOSED

    def test_opens_after_threshold(self):
        """Открывается после достижения порога ошибок."""
        circuit = CircuitBreaker(failure_threshold=3, recovery_timeout=10)

        @circuit
        def failing():
            raise RuntimeError("Failure")

        # 3 ошибки
        for _ in range(3):
            with pytest.raises(RuntimeError):
                failing()

        # Circuit должен быть открыт
        assert circuit.state == CircuitBreaker.OPEN

        # Следующий вызов должен быть заблокирован
        with pytest.raises(CircuitOpenError):
            failing()

    def test_half_open_after_timeout(self):
        """Переход в HALF_OPEN после таймаута."""
        circuit = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)

        @circuit
        def failing():
            raise RuntimeError("Failure")

        # Открываем circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                failing()

        assert circuit.state == CircuitBreaker.OPEN

        # Ждём таймаут
        time.sleep(0.15)

        # Должен перейти в HALF_OPEN
        assert circuit.state == CircuitBreaker.HALF_OPEN

    def test_recovery_from_half_open(self):
        """Восстановление из HALF_OPEN."""
        circuit = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        call_count = 0

        @circuit
        def sometimes_fails():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("Failure")
            return "success"

        # Открываем circuit
        for _ in range(2):
            with pytest.raises(RuntimeError):
                sometimes_fails()

        # Ждём перехода в HALF_OPEN
        time.sleep(0.15)

        # Успешные вызовы должны закрыть circuit
        assert sometimes_fails() == "success"
        assert sometimes_fails() == "success"

        assert circuit.state == CircuitBreaker.CLOSED

    def test_manual_reset(self):
        """Ручной сброс circuit breaker."""
        circuit = CircuitBreaker(failure_threshold=1, recovery_timeout=100)

        @circuit
        def failing():
            raise RuntimeError("Failure")

        with pytest.raises(RuntimeError):
            failing()

        assert circuit.state == CircuitBreaker.OPEN

        circuit.reset()
        assert circuit.state == CircuitBreaker.CLOSED
