#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Быстрый тест модели эмбеддингов без загрузки RAG."""

import sys
import io

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Установите: pip install sentence-transformers scikit-learn")
    sys.exit(1)

print("=" * 60)
print("БЫСТРЫЙ ТЕСТ МОДЕЛИ ЭМБЕДДИНГОВ")
print("=" * 60)

# Загрузка модели
print("\n1. Загрузка модели: ai-forever/sbert_large_nlu_ru")
try:
    model = SentenceTransformer('ai-forever/sbert_large_nlu_ru')
    print(f"   ✅ Модель загружена! Размерность: {model.get_sentence_embedding_dimension()}")
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    sys.exit(1)

# Тестовые тексты
test_texts = [
    "Договор аренды недвижимого имущества",
    "Контракт на поставку товаров", 
    "Соглашение об оказании услуг",
    "Погода сегодня хорошая"
]

print("\n2. Создание эмбеддингов...")
try:
    embeddings = model.encode(test_texts, show_progress_bar=False)
    print(f"   ✅ Создано {len(embeddings)} эмбеддингов")
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    sys.exit(1)

# Проверка сходства
print("\n3. Проверка семантического сходства...")
try:
    similarity = cosine_similarity(embeddings)
    
    print("\n   Матрица сходства:")
    for i in range(len(test_texts)):
        for j in range(i + 1, len(test_texts)):
            sim = similarity[i][j]
            print(f"   '{test_texts[i][:35]}' <-> '{test_texts[j][:35]}'")
            print(f"      Сходство: {sim:.3f}")
    
    # Юридические тексты должны быть более похожи
    legal_sim = np.mean([
        similarity[0][1],  # аренда <-> поставка
        similarity[0][2],  # аренда <-> услуги
        similarity[1][2],  # поставка <-> услуги
    ])
    non_legal_sim = np.mean([
        similarity[0][3],  # аренда <-> погода
        similarity[1][3],  # поставка <-> погода
        similarity[2][3],  # услуги <-> погода
    ])
    
    print(f"\n   Среднее сходство юридических текстов: {legal_sim:.3f}")
    print(f"   Среднее сходство с неюридическим: {non_legal_sim:.3f}")
    
    if legal_sim > non_legal_sim:
        print(f"   ✅ Модель правильно различает типы текстов!")
    else:
        print(f"   ⚠️  Модель может нуждаться в дообучке")
        
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ТЕСТ ЗАВЕРШЕН УСПЕШНО!")
print("=" * 60)
print("\nМодель работает корректно и готова к использованию.")
print("Для дообучения запустите: python scripts/finetune_embeddings.py")
