#!/usr/bin/env python3
"""Тестовый скрипт для проверки установки"""

import sys
import os

def check_imports():
    """Проверка импортов"""
    print("🔍 Проверка импортов...")
    
    requirements = [
        ("pandas", "pandas"),
        ("openpyxl", "openpyxl"),
        ("docx", "python-docx"),
        ("docx2txt", "docx2txt"),
        ("llama_cpp", "llama-cpp-python"),
        ("imapclient", "imapclient"),
        ("schedule", "schedule"),
        ("dotenv", "python-dotenv"),
    ]
    
    all_ok = True
    for module_name, package_name in requirements:
        try:
            __import__(module_name)
            print(f"✅ {package_name}")
        except ImportError:
            print(f"❌ {package_name} не установлен")
            all_ok = False
    
    return all_ok

def check_directories():
    """Проверка структуры директорий"""
    print("\n📁 Проверка директорий...")
    
    directories = [
        "./data",
        "./data/logs",
        "./models",
        "./templates",
        "./agents",
        "./utils"
    ]
    
    for dir_path in directories:
        if os.path.exists(dir_path):
            print(f"✅ {dir_path}")
        else:
            print(f"⚠️  {dir_path} не существует (будет создан автоматически)")

def check_config():
    """Проверка конфигурации"""
    print("\n⚙️  Проверка конфигурации...")
    
    # Проверка .env
    if os.path.exists(".env"):
        print("✅ .env файл найден")
        
        # Читаем ключевые переменные
        with open(".env", "r") as f:
            content = f.read()
            if "EMAIL_ADDRESS" in content:
                print("✅ EMAIL_ADDRESS настроен")
            else:
                print("⚠️  EMAIL_ADDRESS не найден в .env")
                
            if "EMAIL_PASSWORD" in content:
                print("✅ EMAIL_PASSWORD настроен")
            else:
                print("⚠️  EMAIL_PASSWORD не найден в .env")
    else:
        print("❌ .env файл не найден")
        print("   Создайте .env файл из .env.example")

def main():
    print("=" * 50)
    print("Тестирование установки Document Processing Agent")
    print("=" * 50)
    
    # Проверка Python версии
    print(f"🐍 Python версия: {sys.version}")
    
    # Проверка импортов
    imports_ok = check_imports()
    
    # Проверка директорий
    check_directories()
    
    # Проверка конфигурации
    check_config()
    
    print("\n" + "=" * 50)
    if imports_ok:
        print("✅ Все проверки пройдены!")
        print("\nДля запуска агента:")
        print("1. Настройте .env файл")
        print("2. Поместите шаблоны договоров в templates/")
        print("3. Запустите: python main.py --once")
    else:
        print("⚠️  Есть проблемы с установкой")
        print("\nУстановите недостающие пакеты:")
        print("pip install -r requirements.txt")
    
    print("=" * 50)

if __name__ == "__main__":
    main()