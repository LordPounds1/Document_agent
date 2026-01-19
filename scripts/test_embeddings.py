#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки работы модели эмбеддингов.

Проверяет:
- Загрузку модели
- Создание эмбеддингов
- Работу с юридическими текстами
- Интеграцию с RAG системой
"""

import sys
import io
from pathlib import Path

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Добавляем родительскую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_model_loading():
    """Тест 1: Загрузка модели."""
    print("=" * 60)
    print("ТЕСТ 1: Загрузка модели эмбеддингов")
    print("=" * 60)
    
    try:
        from sentence_transformers import SentenceTransformer
        from core.rag import SimpleRAG
        
        print(f"📥 Загрузка модели: {SimpleRAG.EMBEDDING_MODEL}")
        model = SentenceTransformer(SimpleRAG.EMBEDDING_MODEL)
        print(f"✅ Модель успешно загружена!")
        print(f"   Размерность эмбеддингов: {model.get_sentence_embedding_dimension()}")
        return True, model
    except Exception as e:
        print(f"❌ Ошибка загрузки модели: {e}")
        return False, None


def test_embeddings_creation(model):
    """Тест 2: Создание эмбеддингов."""
    print("\n" + "=" * 60)
    print("ТЕСТ 2: Создание эмбеддингов")
    print("=" * 60)
    
    try:
        test_texts = [
            "Договор аренды недвижимого имущества",
            "Контракт на поставку товаров",
            "Соглашение об оказании услуг",
            "Погода сегодня хорошая"  # Не юридический текст
        ]
        
        print(f"📝 Тестовые тексты:")
        for i, text in enumerate(test_texts, 1):
            print(f"   {i}. {text}")
        
        print(f"\n🔄 Создание эмбеддингов...")
        embeddings = model.encode(test_texts, show_progress_bar=True)
        
        print(f"✅ Эмбеддинги созданы успешно!")
        print(f"   Количество: {len(embeddings)}")
        print(f"   Размерность каждого: {embeddings[0].shape}")
        print(f"   Тип: {type(embeddings)}")
        
        return True, embeddings, test_texts
    except Exception as e:
        print(f"❌ Ошибка создания эмбеддингов: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None


def test_similarity(embeddings, texts):
    """Тест 3: Проверка семантического сходства."""
    print("\n" + "=" * 60)
    print("ТЕСТ 3: Семантическое сходство")
    print("=" * 60)
    
    try:
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
        
        # Вычисляем попарное сходство
        similarity_matrix = cosine_similarity(embeddings)
        
        print("📊 Матрица сходства (cosine similarity):")
        print("   (чем ближе к 1.0, тем более похожи тексты)")
        print()
        
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                sim = similarity_matrix[i][j]
                print(f"   '{texts[i][:30]}...' <-> '{texts[j][:30]}...'")
                print(f"      Сходство: {sim:.3f}")
                print()
        
        # Проверяем, что юридические тексты более похожи друг на друга
        legal_similarities = [
            similarity_matrix[0][1],  # аренда <-> поставка
            similarity_matrix[0][2],  # аренда <-> услуги
            similarity_matrix[1][2],    # поставка <-> услуги
        ]
        non_legal_similarities = [
            similarity_matrix[0][3],  # аренда <-> погода
            similarity_matrix[1][3],  # поставка <-> погода
            similarity_matrix[2][3],  # услуги <-> погода
        ]
        
        avg_legal = np.mean(legal_similarities)
        avg_non_legal = np.mean(non_legal_similarities)
        
        print(f"📈 Среднее сходство юридических текстов: {avg_legal:.3f}")
        print(f"📉 Среднее сходство с неюридическим: {avg_non_legal:.3f}")
        
        if avg_legal > avg_non_legal:
            print(f"✅ Модель правильно различает юридические и неюридические тексты!")
        else:
            print(f"⚠️  Модель может не различать типы текстов (возможно, нужна дообучка)")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка вычисления сходства: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rag_integration():
    """Тест 4: Интеграция с RAG системой."""
    print("\n" + "=" * 60)
    print("ТЕСТ 4: Интеграция с RAG системой")
    print("=" * 60)
    
    try:
        from core.rag import SimpleRAG
        
        print("🔧 Инициализация RAG системы...")
        rag = SimpleRAG(templates_dir="templates", use_gpu=False)
        
        print(f"✅ RAG система инициализирована!")
        print(f"   Модель эмбеддингов: {rag.EMBEDDING_MODEL}")
        print(f"   Векторный поиск: {'✅ Включен' if rag.use_vector_search else '❌ Отключен'}")
        print(f"   Загружено шаблонов: {len(rag.documents)}")
        
        if rag.use_vector_search and rag.collection:
            print(f"   Документов в индексе: {rag.collection.count()}")
        
        # Тестовый поиск
        if rag.documents:
            print(f"\n🔍 Тестовый поиск: 'договор аренды'")
            results = rag.search("договор аренды", k=3)
            
            print(f"✅ Найдено результатов: {len(results)}")
            for i, doc in enumerate(results, 1):
                score = doc.score if hasattr(doc, 'score') else 0.0
                filename = doc.metadata.get('filename', 'unknown')
                print(f"   {i}. {filename} (релевантность: {score:.3f})")
        else:
            print("⚠️  Шаблоны не загружены, пропускаем тест поиска")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка интеграции с RAG: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_corpus_loading():
    """Тест 5: Загрузка корпуса (если есть)."""
    print("\n" + "=" * 60)
    print("ТЕСТ 5: Проверка корпуса")
    print("=" * 60)
    
    corpus_file = Path("data/legal_corpus.json")
    
    if not corpus_file.exists():
        print("⚠️  Файл корпуса не найден: data/legal_corpus.json")
        print("   Запустите: python scripts/collect_legal_corpus.py")
        return False
    
    try:
        import json
        
        with open(corpus_file, 'r', encoding='utf-8') as f:
            corpus = json.load(f)
        
        print(f"✅ Корпус загружен успешно!")
        print(f"   Всего документов: {corpus.get('total_documents', 0)}")
        print(f"   Всего абзацев: {len(corpus.get('documents', []))}")
        print(f"   Общая длина: {corpus.get('total_text_length', 0):,} символов")
        print(f"   Создан: {corpus.get('created_at', 'unknown')}")
        
        # Показываем примеры
        if corpus.get('documents'):
            print(f"\n📄 Примеры документов:")
            for i, doc in enumerate(corpus['documents'][:3], 1):
                text_preview = doc['text'][:100] + "..." if len(doc['text']) > 100 else doc['text']
                print(f"   {i}. [{doc.get('source_file', 'unknown')}] {text_preview}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки корпуса: {e}")
        return False


def main():
    """Главная функция - запуск всех тестов."""
    print("\n" + "=" * 60)
    print("🧪 ТЕСТИРОВАНИЕ МОДЕЛИ ЭМБЕДДИНГОВ")
    print("=" * 60)
    print()
    
    results = {}
    
    # Тест 1: Загрузка модели
    success, model = test_model_loading()
    results['model_loading'] = success
    
    if not success:
        print("\n❌ Критическая ошибка: модель не загрузилась!")
        print("   Проверьте:")
        print("   1. Установлен ли sentence-transformers: pip install sentence-transformers")
        print("   2. Доступен ли интернет для скачивания модели")
        print("   3. Правильно ли указана модель в core/rag.py")
        sys.exit(1)
    
    # Тест 2: Создание эмбеддингов
    success, embeddings, texts = test_embeddings_creation(model)
    results['embeddings_creation'] = success
    
    if success:
        # Тест 3: Сходство
        results['similarity'] = test_similarity(embeddings, texts)
    
    # Тест 4: RAG интеграция
    results['rag_integration'] = test_rag_integration()
    
    # Тест 5: Корпус
    results['corpus'] = test_corpus_loading()
    
    # Итоги
    print("\n" + "=" * 60)
    print("📊 ИТОГИ ТЕСТИРОВАНИЯ")
    print("=" * 60)
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {test_name:20s}: {status}")
    
    print(f"\n   Всего тестов: {total}")
    print(f"   Пройдено: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 Все тесты пройдены! Модель работает корректно.")
        return 0
    else:
        print(f"\n⚠️  Некоторые тесты не пройдены ({total - passed} из {total})")
        return 1


if __name__ == '__main__':
    sys.exit(main())
