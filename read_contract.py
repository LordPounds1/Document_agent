#!/usr/bin/env python
import pandas as pd
import sys

file_path = r'z:\Data With Python\document_processing_agent\contracts\REG-2025-000021.xlsx'
print(f"Читаю файл: {file_path}")

try:
    df = pd.read_excel(file_path)
    print("\n" + "="*80)
    print("СОДЕРЖИМОЕ REG-2025-000021.xlsx")
    print("="*80)
    print(df.to_string())
    print("\n" + "="*80)
    print("КОЛОНКИ:")
    for col in df.columns:
        print(f"  - {col}")
    print("\n" + "="*80)
    print("ЗНАЧЕНИЯ (построчно):")
    for idx, row in df.iterrows():
        print(f"\nСтрока {idx}:")
        for col, val in row.items():
            val_str = str(val)[:100] if pd.notna(val) else "NaN"
            print(f"  {col}: {val_str}")
except Exception as e:
    print(f"Ошибка: {e}")
    sys.exit(1)
