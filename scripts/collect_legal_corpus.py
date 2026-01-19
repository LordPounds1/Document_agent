#!/usr/bin/env python3
"""
Скрипт для сбора корпуса юридических документов из папки templates.

Собирает все DOCX файлы, извлекает текст и сохраняет в JSON для дообучения эмбеддингов.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# Добавляем родительскую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import docx2txt
except ImportError:
    print("❌ Установите docx2txt: pip install docx2txt")
    sys.exit(1)


def extract_text_from_docx(file_path: Path) -> str:
    """Извлечение текста из DOCX файла."""
    try:
        text = docx2txt.process(str(file_path))
        return text.strip()
    except Exception as e:
        print(f"⚠️  Ошибка чтения {file_path.name}: {e}")
        return ""


def collect_corpus(templates_dir: Path, output_file: Path) -> dict:
    """Сбор корпуса из DOCX файлов.
    
    Args:
        templates_dir: Директория с шаблонами договоров
        output_file: Файл для сохранения корпуса (JSON)
    
    Returns:
        Статистика сбора
    """
    if not templates_dir.exists():
        print(f"❌ Директория не найдена: {templates_dir}")
        return {"success": False, "error": "Directory not found"}
    
    corpus = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "source_dir": str(templates_dir),
        "total_documents": 0,
        "total_text_length": 0,
        "documents": []
    }
    
    docx_files = list(templates_dir.glob("*.docx"))
    
    if not docx_files:
        print(f"⚠️  DOCX файлы не найдены в {templates_dir}")
        return {"success": False, "error": "No DOCX files found"}
    
    print(f"📄 Найдено {len(docx_files)} DOCX файлов")
    print("🔍 Извлечение текста...")
    
    for i, docx_file in enumerate(docx_files, 1):
        print(f"  [{i}/{len(docx_files)}] Обработка: {docx_file.name}")
        
        text = extract_text_from_docx(docx_file)
        
        if not text or len(text) < 100:
            print(f"    ⚠️  Пропущен (слишком короткий или пустой)")
            continue
        
        # Разбиваем на предложения/абзацы для обучения
        # Используем абзацы как отдельные примеры
        paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 50]
        
        if not paragraphs:
            # Если нет абзацев, разбиваем по предложениям
            sentences = [s.strip() for s in text.replace('. ', '.\n').split('\n') 
                        if len(s.strip()) > 30]
            paragraphs = sentences
        
        for para_idx, paragraph in enumerate(paragraphs):
            corpus["documents"].append({
                "id": f"{docx_file.stem}_{para_idx}",
                "source_file": docx_file.name,
                "text": paragraph,
                "length": len(paragraph),
                "type": "legal_document"
            })
        
        corpus["total_documents"] += 1
        corpus["total_text_length"] += len(text)
    
    # Сохраняем корпус
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    
    total_paragraphs = len(corpus["documents"])
    avg_length = corpus["total_text_length"] / corpus["total_documents"] if corpus["total_documents"] > 0 else 0
    
    print(f"\n✅ Корпус собран успешно!")
    print(f"   📁 Файлов обработано: {corpus['total_documents']}")
    print(f"   📝 Абзацев/предложений: {total_paragraphs}")
    print(f"   📊 Общая длина текста: {corpus['total_text_length']:,} символов")
    print(f"   📈 Средняя длина документа: {avg_length:.0f} символов")
    print(f"   💾 Сохранено в: {output_file}")
    
    return {
        "success": True,
        "total_files": corpus["total_documents"],
        "total_paragraphs": total_paragraphs,
        "total_length": corpus["total_text_length"],
        "output_file": str(output_file)
    }


def main():
    """Главная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Сбор корпуса юридических документов из папки templates'
    )
    parser.add_argument(
        '--templates-dir',
        type=str,
        default='templates',
        help='Директория с шаблонами договоров (по умолчанию: templates)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/legal_corpus.json',
        help='Файл для сохранения корпуса (по умолчанию: data/legal_corpus.json)'
    )
    
    args = parser.parse_args()
    
    templates_dir = Path(args.templates_dir)
    output_file = Path(args.output)
    
    result = collect_corpus(templates_dir, output_file)
    
    if not result.get("success"):
        print(f"\n❌ Ошибка: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
