#!/usr/bin/env python3
import os
import sys
from pathlib import Path

def check_model():
    """Проверка наличия модели"""
    models_dir = Path("./models")
    models_dir.mkdir(exist_ok=True)
    
    # Проверяем существующие модели
    model_files = list(models_dir.glob("*.gguf"))
    
    # Фильтруем только валидные модели (размер > 10 MB)
    valid_models = []
    for model_file in model_files:
        file_size_mb = model_file.stat().st_size / (1024 * 1024)
        if file_size_mb < 10:
            print(f"⚠️  Пропущен поврежденный файл: {model_file.name} (размер: {file_size_mb:.2f} MB)")
            # Удаляем поврежденный файл
            try:
                model_file.unlink()
                print(f"   Удален поврежденный файл")
            except:
                pass
        else:
            valid_models.append(model_file)
    
    if valid_models:
        print(f"✅ Найдены валидные модели: {[m.name for m in valid_models]}")
        return str(valid_models[0])
    
    print("❌ Модели не найдены в папке models/")
    print("\n📥 Скачать модели можно:")
    print("1. Saiga Mistral 7B (рекомендуемая): https://huggingface.co/IlyaGusev/saiga_mistral_7b_gguf")
    print("2. Saiga Llama 3 8B: https://huggingface.co/IlyaGusev/saiga_llama3_8b_gguf")
    print("3. Saiga Mistral 7B (квантизованная): https://huggingface.co/IlyaGusev/saiga_mistral_7b_gguf/resolve/main/model-q4_K_M.gguf")
    
    choice = input("\nСкачать модель? (y/n): ")
    if choice.lower() == 'y':
        # Используем более простую модель для начала
        import requests
        url = "https://huggingface.co/IlyaGusev/saiga_mistral_7b_gguf/resolve/main/model-q4_K_M.gguf"
        model_path = models_dir / "saiga_mistral_7b_q4.gguf"
        
        print(f"Скачивание {url}...")
        print("⚠️  ВНИМАНИЕ: Модель весит ~4-5 GB, скачивание может занять время")
        
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Проверяем успешность запроса
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(model_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        if downloaded % (10 * 1024 * 1024) == 0:  # Каждые 10 MB
                            print(f"   Скачано: {downloaded / (1024*1024):.1f} MB ({percent:.1f}%)")
        
        # Проверяем размер скачанного файла
        file_size_mb = model_path.stat().st_size / (1024 * 1024)
        if file_size_mb < 10:
            print(f"❌ ОШИБКА: Файл слишком маленький ({file_size_mb:.2f} MB)")
            print("   Возможно, скачивание не завершилось")
            model_path.unlink()
            return None
        
        print(f"✅ Модель скачана: {model_path} (размер: {file_size_mb:.2f} MB)")
        return str(model_path)
    
    return None

def test_llama_cpp():
    """Тестирование llama-cpp"""
    try:
        from llama_cpp import Llama
        print("✅ llama-cpp-python установлен")
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта llama-cpp: {e}")
        print("\nУстановите llama-cpp-python:")
        print("pip install llama-cpp-python")
        return False

def main():
    print("🔧 Проверка и настройка модели")
    print("=" * 50)
    
    # Проверяем llama-cpp
    if not test_llama_cpp():
        sys.exit(1)
    
    # Проверяем модель
    model_path = check_model()
    
    if model_path:
        print(f"\n✅ Модель готова: {model_path}")
        print("\nЧтобы использовать модель, добавьте в .env:")
        print(f"MODEL_PATH={model_path}")
        
        # Тестируем загрузку модели
        print("\n🧪 Тестирование загрузки модели...")
        try:
            from llama_cpp import Llama
            llm = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_threads=4,
                verbose=False
            )
            print("✅ Модель успешно загружена!")
            
            # Быстрый тест
            print("\n🧪 Быстрый тест генерации...")
            response = llm("Привет, мир!", max_tokens=10)
            print(f"Ответ модели: {response['choices'][0]['text']}")
            
        except Exception as e:
            print(f"❌ Ошибка загрузки модели: {e}")
            print("\nВозможные решения:")
            print("1. Убедитесь, что модель скачана полностью")
            print("2. Попробуйте другую модель")
            print("3. Проверьте доступную оперативную память")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    main()