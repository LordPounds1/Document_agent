#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скрипт для дообучения модели эмбеддингов на юридических документах.

Использует sentence-transformers для fine-tuning модели на корпусе юридических документов.
"""

import json
import sys
import io
from pathlib import Path
from datetime import datetime

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Добавляем родительскую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from sentence_transformers import SentenceTransformer, InputExample, losses, evaluation
    from torch.utils.data import DataLoader
    import torch
except ImportError:
    print("❌ Установите зависимости:")
    print("   pip install sentence-transformers torch")
    sys.exit(1)


def load_corpus(corpus_file: Path) -> list[dict]:
    """Загрузка корпуса из JSON файла."""
    if not corpus_file.exists():
        print(f"[!] Файл корпуса не найден: {corpus_file}")
        sys.exit(1)
    
    with open(corpus_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
        print(f"[*] Загружено {len(data['documents'])} документов из корпуса")
    return data['documents']


def create_training_examples(documents: list[dict], strategy: str = "contrastive") -> list[InputExample]:
    """Создание примеров для обучения.
    
    Args:
        documents: Список документов из корпуса
        strategy: Стратегия обучения
            - "contrastive": Похожие документы = 1.0, разные = 0.0
            - "triplet": Триплеты (anchor, positive, negative)
    
    Returns:
        Список InputExample для обучения
    """
    examples = []
    
    if strategy == "contrastive":
        # Создаём пары похожих документов (из одного файла = похожие)
        # и разные документы (из разных файлов = разные)
        
        # Группируем по исходным файлам
        by_file: dict[str, list[dict]] = {}
        for doc in documents:
            source = doc.get('source_file', 'unknown')
            if source not in by_file:
                by_file[source] = []
            by_file[source].append(doc)
        
        # Похожие пары (из одного файла)
        for file_docs in by_file.values():
            if len(file_docs) >= 2:
                # Берём пары соседних абзацев как похожие
                for i in range(len(file_docs) - 1):
                    examples.append(InputExample(
                        texts=[file_docs[i]['text'], file_docs[i+1]['text']],
                        label=1.0  # Похожие
                    ))
        
        # Разные пары (из разных файлов)
        file_list = list(by_file.values())
        for i, file1_docs in enumerate(file_list):
            for file2_docs in file_list[i+1:]:
                # Берём по одному документу из каждого файла
                if file1_docs and file2_docs:
                    examples.append(InputExample(
                        texts=[file1_docs[0]['text'], file2_docs[0]['text']],
                        label=0.0  # Разные
                    ))
                    # Ограничиваем количество, чтобы не было слишком много
                    if len(examples) >= 1000:
                        break
            if len(examples) >= 1000:
                break
    
    print(f"[*] Создано {len(examples)} примеров для обучения")
    return examples


def finetune_model(
    base_model: str,
    corpus_file: Path,
    output_dir: Path,
    epochs: int = 3,
    batch_size: int = 16,
    use_gpu: bool = True
):
    """Дообучение модели эмбеддингов.
    
    Args:
        base_model: Базовая модель (например, 'ai-forever/sbert_large_nlu_ru')
        corpus_file: Файл с корпусом (JSON)
        output_dir: Директория для сохранения дообученной модели
        epochs: Количество эпох
        batch_size: Размер батча
        use_gpu: Использовать GPU если доступен
    """
    print(f"[*] Начало дообучения модели: {base_model}")
    print(f"[*] Корпус: {corpus_file}")
    print(f"[*] Выходная директория: {output_dir}")
    
    # Проверка GPU
    device = 'cuda' if use_gpu and torch.cuda.is_available() else 'cpu'
    print(f"[*] Устройство: {device}")
    
    # Загрузка базовой модели
    print(f"\n[*] Загрузка базовой модели...")
    model = SentenceTransformer(base_model, device=device)
    
    # Загрузка корпуса
    print(f"[*] Загрузка корпуса...")
    documents = load_corpus(corpus_file)
    
    if len(documents) < 10:
        print("[!] Внимание: Мало документов для обучения. Рекомендуется минимум 20-30 документов.")
    
    # Создание примеров для обучения
    print(f"[*] Создание примеров для обучения...")
    train_examples = create_training_examples(documents, strategy="contrastive")
    
    if len(train_examples) < 10:
        print("[!] Недостаточно примеров для обучения. Нужно минимум 10 пар.")
        sys.exit(1)
    
    # Ограничиваем количество примеров для ускорения (максимум 5000)
    if len(train_examples) > 5000:
        print(f"[*] Ограничение примеров до 5000 для ускорения (было {len(train_examples)})")
        train_examples = train_examples[:5000]
    
    # Разделение на train/validation (80/20)
    split_idx = int(len(train_examples) * 0.8)
    train_data = train_examples[:split_idx]
    val_data = train_examples[split_idx:]
    
    print(f"   Обучающих примеров: {len(train_data)}")
    print(f"   Валидационных примеров: {len(val_data)}")
    
    # Создание DataLoader
    train_dataloader = DataLoader(train_data, shuffle=True, batch_size=batch_size)
    
    # Функция потерь (CosineSimilarityLoss для контрастивного обучения)
    train_loss = losses.CosineSimilarityLoss(model)
    
    # Валидация (опционально)
    evaluator = None
    if val_data:
        # Создаём evaluator для мониторинга качества
        val_sentences1 = [ex.texts[0] for ex in val_data]
        val_sentences2 = [ex.texts[1] for ex in val_data]
        val_scores = [ex.label for ex in val_data]
        
        evaluator = evaluation.EmbeddingSimilarityEvaluator(
            val_sentences1, val_sentences2, val_scores
        )
    
    # Обучение
    print(f"\n[*] Начало обучения ({epochs} эпох)...")
    print("    Это может занять некоторое время...")
    
    warmup_steps = int(len(train_dataloader) * epochs * 0.1)  # 10% от общего числа шагов
    
    model.fit(
        train_objectives=[(train_dataloader, train_loss)],
        epochs=epochs,
        warmup_steps=warmup_steps,
        evaluator=evaluator,
        evaluation_steps=100,
        output_path=str(output_dir),
        show_progress_bar=True
    )
    
    print(f"\n[+] Обучение завершено!")
    print(f"[+] Модель сохранена в: {output_dir}")
    print(f"\n[*] Для использования в проекте:")
    print(f"    1. Обновите EMBEDDING_MODEL в core/rag.py на: {output_dir}")
    print(f"    2. Или используйте относительный путь: {output_dir.relative_to(Path.cwd())}")


def main():
    """Главная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Дообучение модели эмбеддингов на юридических документах'
    )
    parser.add_argument(
        '--base-model',
        type=str,
        default='ai-forever/sbert_large_nlu_ru',
        help='Базовая модель для дообучения (по умолчанию: ai-forever/sbert_large_nlu_ru)'
    )
    parser.add_argument(
        '--corpus',
        type=str,
        default='data/legal_corpus.json',
        help='Файл с корпусом (по умолчанию: data/legal_corpus.json)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='models/embeddings_finetuned',
        help='Директория для сохранения модели (по умолчанию: models/embeddings_finetuned)'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=3,
        help='Количество эпох (по умолчанию: 3)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=16,
        help='Размер батча (по умолчанию: 16)'
    )
    parser.add_argument(
        '--no-gpu',
        action='store_true',
        help='Не использовать GPU (только CPU)'
    )
    
    args = parser.parse_args()
    
    corpus_file = Path(args.corpus)
    output_dir = Path(args.output)
    
    if not corpus_file.exists():
        print(f"[!] Файл корпуса не найден: {corpus_file}")
        print(f"    Сначала запустите: python scripts/collect_legal_corpus.py")
        sys.exit(1)
    
    finetune_model(
        base_model=args.base_model,
        corpus_file=corpus_file,
        output_dir=output_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        use_gpu=not args.no_gpu
    )


if __name__ == '__main__':
    main()
