"""Simplified LLM Client - обёртка над llama-cpp-python"""

import logging
import json
import re
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class LLMClient:
    """Упрощённый клиент для работы с локальной LLM"""
    
    # Thread-safety: ограничение параллельных GPU операций
    from threading import Semaphore
    _inference_semaphore = Semaphore(2)  # Max 2 concurrent requests
    
    def __init__(self, model_path: str, n_ctx: int = 2048, n_gpu_layers: int = -1):
        """
        Args:
            model_path: Путь к GGUF модели
            n_ctx: Размер контекста
            n_gpu_layers: Количество слоёв на GPU (-1 = все)
        """
        self.model_path = model_path
        self.llm = None
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self._inference_count = 0
        self._init_model(n_ctx, n_gpu_layers)
    
    def _init_model(self, n_ctx: int, n_gpu_layers: int):
        """Инициализация модели"""
        try:
            from llama_cpp import Llama
            
            logger.info(f"Loading model: {self.model_path}")
            logger.info(f"GPU layers: {n_gpu_layers}, context: {n_ctx}")
            
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=n_ctx,
                n_gpu_layers=n_gpu_layers,
                n_batch=512,
                n_threads=1,
                use_mlock=True,
                verbose=False
            )
            
            logger.info("✅ Model loaded successfully")
            logger.info(f"VRAM limit: 2 concurrent requests, context={n_ctx}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.llm = None
    
    def generate(self, prompt: str, max_tokens: int = 512, 
                 temperature: float = 0.1, stop: Optional[list] = None) -> str:
        """Генерация текста с concurrency control
        
        Args:
            prompt: Промпт
            max_tokens: Максимум токенов
            temperature: Температура (0.0-1.0)
            stop: Стоп-последовательности
            
        Returns:
            Сгенерированный текст
        """
        if not self.llm:
            logger.error("Model not initialized")
            return ""
        
        # Acquire semaphore для ограничения concurrent GPU operations
        with self._inference_semaphore:
            self._inference_count += 1
            
            try:
                result = self.llm(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stop=stop or ["</s>", "Пользователь:", "User:"],
                    echo=False
                )
                
                text = result.get('choices', [{}])[0].get('text', '').strip()
                
                # 🚀 GPU cleanup после inference для предотвращения OOM
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        torch.cuda.synchronize()
                        logger.debug("[GPU] Cache cleared after inference")
                except ImportError:
                    pass  # torch not available
                except Exception as e:
                    logger.warning(f"GPU cleanup failed: {e}")
                
                # Warn если много инференсов (потенциальный memory leak)
                if self._inference_count % 50 == 0:
                    logger.info(f"[LLM] Completed {self._inference_count} inferences")
                
                return text
            except Exception as e:
                logger.error(f"Generation failed: {e}")
                return ""
    
    def close(self):
        """Explicitly close llama.cpp context to prevent memory leak"""
        if self.llm:
            try:
                # llama-cpp-python context cleanup
                if hasattr(self.llm, 'close'):
                    self.llm.close()
                self.llm = None
                logger.info("✅ LLM context closed (preventing memory leak)")
            except Exception as e:
                logger.warning(f"Error closing LLM context: {e}")
    
    def __del__(self):
        """Ensure cleanup on garbage collection"""
        self.close()
    
    def generate_json(self, prompt: str, schema: Dict[str, str], 
                     max_tokens: int = 512) -> Dict[str, Any]:
        """Генерация JSON с валидацией схемы
        
        Args:
            prompt: Промпт с инструкцией вернуть JSON
            schema: Описание полей {field: description}
            max_tokens: Максимум токенов
            
        Returns:
            Словарь с результатами
        """
        # Добавляем в промпт требование JSON формата
        full_prompt = f"""{prompt}

Верни результат СТРОГО в формате JSON без комментариев:
{{
{chr(10).join(f'  "{field}": "..."' for field in schema.keys())}
}}
"""
        
        text = self.generate(full_prompt, max_tokens=max_tokens, temperature=0.1)
        
        # Пытаемся распарсить JSON
        try:
            # Ищем JSON блок
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                result = json.loads(json_str)
                logger.debug(f"Parsed JSON successfully")
                return result
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed: {e}")
        
        # Fallback: извлекаем поля regex
        result = {}
        for field in schema.keys():
            pattern = rf'"{field}"\s*:\s*"([^"]*)"'
            match = re.search(pattern, text)
            if match:
                result[field] = match.group(1)
            else:
                result[field] = ""
        
        logger.debug(f"Extracted fields via regex: {list(result.keys())}")
        return result
