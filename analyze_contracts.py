#!/usr/bin/env python3
"""
Contract Database Analysis Tool
Analyzes 585 contracts: types, parties, amounts, dates, clustering
"""
import os
import json
import csv
from pathlib import Path
from collections import defaultdict
import re
from datetime import datetime

def extract_metadata(filename):
    """Extract likely metadata from filename"""
    metadata = {
        "filename": filename,
        "party": None,
        "type": None,
        "number": None,
        "year": None,
    }
    
    # Extract contract number (№XX pattern)
    number_match = re.search(r'№(\d+)', filename)
    if number_match:
        metadata["number"] = number_match.group(1)
    
    # Extract year (20XX pattern)
    year_match = re.search(r'(20\d{2})', filename)
    if year_match:
        metadata["year"] = year_match.group(1)
    
    # Identify contract type by keywords
    filename_lower = filename.lower()
    
    contract_types = {
        "Договор": ["договор"],
        "Доверенность": ["доверенность"],
        "Арендное соглашение": ["аренда"],
        "Дополнительное соглашение": ["доп", "дополнител"],
        "Приказ": ["приказ"],
        "Письмо": ["письмо", "pismo"],
        "Акт": ["акт"],
        "Решение": ["решение"],
        "Протокол": ["протокол"],
        "Расписка": ["расписка"],
        "Спецификация": ["спецификац"],
    }
    
    for contract_type, keywords in contract_types.items():
        if any(kw in filename_lower for kw in keywords):
            metadata["type"] = contract_type
            break
    
    # Extract party name (common organization names)
    parties = [
        "СДС", "Аманат", "Комфорт", "Акбарыс", "БИОС",
        "Алтын", "Азат", "Актобе", "Рост", "Коптлеуов",
        "Махатов", "Нагауов", "ТКА", "АМК", "Стронеф",
        "Дроздов", "Ощепков", "Саджар", "Мамыр", "Шагров",
    ]
    
    for party in parties:
        if party in filename:
            metadata["party"] = party
            break
    
    return metadata

def classify_contract(filename):
    """Classify contract by type"""
    filename_lower = filename.lower()
    
    if any(x in filename_lower for x in ["аренда", "арендатор", "arenda"]):
        return "Аренда/Lease"
    elif any(x in filename_lower for x in ["доверенность"]):
        return "Доверенность/Power of Attorney"
    elif any(x in filename_lower for x in ["поставка", "продажа", "купля"]):
        return "Покупка-продажа/Supply"
    elif any(x in filename_lower for x in ["подряд", "строи", "монтаж", "отделка", "демонтаж"]):
        return "Строительство/Construction"
    elif any(x in filename_lower for x in ["услуг", "обслуж", "сервис", "мониторинг"]):
        return "Услуги/Services"
    elif any(x in filename_lower for x in ["доп соглашение", "дополнител"]):
        return "Доп. соглашение/Amendment"
    elif any(x in filename_lower for x in ["приказ"]):
        return "Приказ/Order"
    elif any(x in filename_lower for x in ["письмо", "pismo"]):
        return "Письмо/Letter"
    elif any(x in filename_lower for x in ["акт", "приемка"]):
        return "Акт/Act"
    else:
        return "Другое/Other"

def analyze_templates_directory():
    """Analyze all contracts in templates directory"""
    templates_dir = Path("templates")
    
    if not templates_dir.exists():
        print("❌ templates directory not found")
        return
    
    print("=" * 70)
    print("CONTRACT DATABASE ANALYSIS")
    print("=" * 70)
    
    # Collect statistics
    files = list(templates_dir.glob("*"))
    total_files = len(files)
    
    # File types
    file_types = defaultdict(int)
    file_sizes = defaultdict(int)
    
    # Contract classification
    contract_types = defaultdict(int)
    
    # Parties
    parties = defaultdict(int)
    
    # Years
    years = defaultdict(int)
    
    # Numbers
    numbers_set = set()
    
    # Metadata
    all_metadata = []
    
    print(f"\nAnalyzing {total_files} contracts...")
    
    for file_path in files:
        if file_path.is_file():
            # File type
            ext = file_path.suffix.lower()
            file_types[ext] += 1
            file_sizes[ext] += file_path.stat().st_size
            
            # Classification
            contract_type = classify_contract(file_path.name)
            contract_types[contract_type] += 1
            
            # Metadata
            metadata = extract_metadata(file_path.name)
            metadata["ext"] = ext
            metadata["size_kb"] = file_path.stat().st_size / 1024
            metadata["contract_type"] = contract_type
            
            all_metadata.append(metadata)
            
            if metadata["party"]:
                parties[metadata["party"]] += 1
            
            if metadata["year"]:
                years[metadata["year"]] += 1
            
            if metadata["number"]:
                numbers_set.add(int(metadata["number"]))
    
    # ===== PRINT RESULTS =====
    
    print(f"\n✓ TOTAL CONTRACTS: {total_files}")
    
    print("\n📁 FILE TYPES:")
    for ext, count in sorted(file_types.items(), key=lambda x: x[1], reverse=True):
        size_mb = file_sizes[ext] / (1024 * 1024)
        percentage = (count / total_files) * 100
        print(f"  {ext:<6} {count:>4} files ({percentage:>5.1f}%) - {size_mb:>6.1f} MB")
    
    total_size_mb = sum(file_sizes.values()) / (1024 * 1024)
    print(f"\n  Total size: {total_size_mb:.1f} MB")
    
    print("\n📋 CONTRACT TYPES:")
    for contract_type, count in sorted(contract_types.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_files) * 100
        print(f"  {contract_type:<40} {count:>4} ({percentage:>5.1f}%)")
    
    print("\n👥 TOP PARTIES (Organizations/Individuals):")
    top_parties = sorted(parties.items(), key=lambda x: x[1], reverse=True)[:15]
    for party, count in top_parties:
        percentage = (count / total_files) * 100
        print(f"  {party:<30} {count:>4} contracts ({percentage:>5.1f}%)")
    
    if len(parties) > 15:
        print(f"  ... and {len(parties) - 15} more parties")
    
    print("\n📅 CONTRACTS BY YEAR:")
    for year in sorted(years.keys()):
        count = years[year]
        percentage = (count / total_files) * 100
        print(f"  {year}: {count:>4} contracts ({percentage:>5.1f}%)")
    
    if numbers_set:
        print(f"\n🔢 CONTRACT NUMBERS:")
        print(f"  Range: {min(numbers_set)} - {max(numbers_set)}")
        print(f"  Count with numbers: {len(numbers_set)}")
    
    # Save detailed CSV
    print(f"\n💾 Saving detailed analysis...")
    csv_file = "contract_analysis.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_metadata[0].keys())
        writer.writeheader()
        writer.writerows(all_metadata)
    print(f"  ✓ {csv_file} ({len(all_metadata)} records)")
    
    # Save JSON summary
    summary = {
        "analysis_date": datetime.now().isoformat(),
        "total_contracts": total_files,
        "total_size_mb": round(total_size_mb, 2),
        "file_types": dict(file_types),
        "contract_types": dict(contract_types),
        "top_parties": dict(top_parties),
        "years": dict(sorted(years.items())),
        "unique_numbers": len(numbers_set),
        "unique_parties": len(parties),
    }
    
    json_file = "contract_analysis.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  ✓ {json_file}")
    
    # Save contracts by type
    contracts_by_type = defaultdict(list)
    for metadata in all_metadata:
        contracts_by_type[metadata["contract_type"]].append(metadata["filename"])
    
    type_file = "contracts_by_type.json"
    with open(type_file, "w", encoding="utf-8") as f:
        json.dump(dict(contracts_by_type), f, indent=2, ensure_ascii=False)
    print(f"  ✓ {type_file}")
    
    print("\n" + "=" * 70)
    print("✅ ANALYSIS COMPLETE")
    print("=" * 70)
    
    print("\nFiles generated:")
    print(f"  1. {csv_file} - Full details for all contracts")
    print(f"  2. {json_file} - Summary statistics")
    print(f"  3. {type_file} - Contracts organized by type")
    
    print("\nNext steps:")
    print("  1. python main.py --index-templates (index into RAG)")
    print("  2. python main.py --test --rag (test semantic search)")
    print("  3. python main.py --stats (show RAG statistics)")

if __name__ == "__main__":
    analyze_templates_directory()
