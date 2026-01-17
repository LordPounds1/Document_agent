"""
Скрипт для шифрования/расшифровки шаблонов договоров.

Использует Fernet (симметричное шифрование) из библиотеки cryptography.

Использование:
    # Генерация ключа (один раз)
    python encrypt_templates.py --generate-key

    # Шифрование
    python encrypt_templates.py --encrypt

    # Расшифровка
    python encrypt_templates.py --decrypt

Ключ хранится в переменной окружения TEMPLATES_KEY или файле .templates_key
"""

import argparse
import os
import sys
from pathlib import Path
# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_key():
    """Получение ключа шифрования"""
    # Сначала проверяем переменную окружения
    key = os.environ.get('TEMPLATES_KEY')
    if key:
        return key.encode()

    # Затем проверяем файл
    key_file = Path(__file__).parent.parent / '.templates_key'
    if key_file.exists():
        return key_file.read_bytes().strip()

    return None


def generate_key():
    """Генерация нового ключа"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("❌ Установите cryptography: pip install cryptography")
        return None

    key = Fernet.generate_key()
    key_file = Path(__file__).parent.parent / '.templates_key'
    key_file.write_bytes(key)

    print(f"✅ Ключ сохранён в {key_file}")
    print("⚠️  Добавьте .templates_key в .gitignore!")
    print("\n📋 Для продакшена используйте переменную окружения:")
    print(f"   TEMPLATES_KEY={key.decode()}")

    return key


def encrypt_templates():
    """Шифрование всех .docx файлов в папке templates"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("❌ Установите cryptography: pip install cryptography")
        return

    key = get_key()
    if not key:
        print("❌ Ключ не найден. Сначала выполните: python encrypt_templates.py --generate-key")
        return

    fernet = Fernet(key)
    templates_dir = Path(__file__).parent.parent / 'templates'
    encrypted_dir = Path(__file__).parent.parent / 'templates_encrypted'
    encrypted_dir.mkdir(exist_ok=True)

    count = 0
    for docx_file in templates_dir.glob('*.docx'):
        data = docx_file.read_bytes()
        encrypted = fernet.encrypt(data)

        enc_file = encrypted_dir / f"{docx_file.stem}.enc"
        enc_file.write_bytes(encrypted)
        count += 1
        print(f"🔒 Зашифрован: {docx_file.name} -> {enc_file.name}")

    print(f"\n✅ Зашифровано файлов: {count}")
    print(f"📁 Зашифрованные файлы в: {encrypted_dir}")
    print("\n⚠️  Теперь можно удалить оригиналы из templates/ и закоммитить templates_encrypted/")


def decrypt_templates():
    """Расшифровка всех .enc файлов в папку templates"""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        print("❌ Установите cryptography: pip install cryptography")
        return

    key = get_key()
    if not key:
        print("❌ Ключ не найден. Установите TEMPLATES_KEY или создайте .templates_key")
        return

    fernet = Fernet(key)
    templates_dir = Path(__file__).parent.parent / 'templates'
    encrypted_dir = Path(__file__).parent.parent / 'templates_encrypted'

    if not encrypted_dir.exists():
        print(f"❌ Папка {encrypted_dir} не найдена")
        return

    templates_dir.mkdir(exist_ok=True)

    count = 0
    for enc_file in encrypted_dir.glob('*.enc'):
        try:
            data = enc_file.read_bytes()
            decrypted = fernet.decrypt(data)

            docx_file = templates_dir / f"{enc_file.stem}.docx"
            docx_file.write_bytes(decrypted)
            count += 1
            print(f"🔓 Расшифрован: {enc_file.name} -> {docx_file.name}")
        except Exception as e:
            print(f"❌ Ошибка расшифровки {enc_file.name}: {e}")

    print(f"\n✅ Расшифровано файлов: {count}")


def main():
    parser = argparse.ArgumentParser(description='Шифрование/расшифровка шаблонов договоров')
    parser.add_argument('--generate-key', action='store_true', help='Сгенерировать новый ключ')
    parser.add_argument('--encrypt', action='store_true', help='Зашифровать шаблоны')
    parser.add_argument('--decrypt', action='store_true', help='Расшифровать шаблоны')

    args = parser.parse_args()

    if args.generate_key:
        generate_key()
    elif args.encrypt:
        encrypt_templates()
    elif args.decrypt:
        decrypt_templates()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

