"""
Launcher для Document Processing Agent
Запускает Streamlit приложение и открывает браузер
"""

import subprocess
import sys
import os
import time
import webbrowser
from pathlib import Path

def main():
    # Определяем директорию приложения
    if getattr(sys, 'frozen', False):
        # Запуск из exe
        app_dir = Path(sys.executable).parent
    else:
        # Запуск из Python
        app_dir = Path(__file__).parent
    
    os.chdir(app_dir)
    
    # Путь к streamlit приложению
    app_path = app_dir / "app_streamlit.py"
    
    if not app_path.exists():
        print(f"❌ Файл {app_path} не найден!")
        input("Нажмите Enter для выхода...")
        return
    
    print("=" * 50)
    print("📄 Document Processing Agent")
    print("=" * 50)
    print()
    print("🚀 Запуск приложения...")
    print()
    
    # Запускаем Streamlit
    port = 8501
    
    # Формируем команду
    if getattr(sys, 'frozen', False):
        # Для exe используем системный Python
        cmd = [
            sys.executable.replace('launcher.exe', 'python.exe'),
            "-m", "streamlit", "run", 
            str(app_path),
            "--server.port", str(port),
            "--server.headless", "true"
        ]
        # Если нет python.exe рядом, используем streamlit напрямую
        streamlit_path = app_dir / "Scripts" / "streamlit.exe"
        if streamlit_path.exists():
            cmd = [str(streamlit_path), "run", str(app_path), "--server.port", str(port), "--server.headless", "true"]
        else:
            # Пробуем через PATH
            cmd = ["streamlit", "run", str(app_path), "--server.port", str(port), "--server.headless", "true"]
    else:
        cmd = [
            sys.executable, "-m", "streamlit", "run", 
            str(app_path),
            "--server.port", str(port),
            "--server.headless", "true"
        ]
    
    print(f"📍 Команда: {' '.join(cmd)}")
    print()
    
    try:
        # Запускаем процесс
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(app_dir)
        )
        
        # Ждём запуска
        print("⏳ Ожидание запуска сервера...")
        time.sleep(3)
        
        # Открываем браузер
        url = f"http://localhost:{port}"
        print(f"🌐 Открытие браузера: {url}")
        webbrowser.open(url)
        
        print()
        print("=" * 50)
        print("✅ Приложение запущено!")
        print(f"🌐 Адрес: {url}")
        print()
        print("Для остановки нажмите Ctrl+C или закройте это окно")
        print("=" * 50)
        print()
        
        # Читаем вывод
        for line in process.stdout:
            print(line, end='')
        
        process.wait()
        
    except KeyboardInterrupt:
        print("\n🛑 Остановка приложения...")
        process.terminate()
    except FileNotFoundError:
        print("❌ Streamlit не найден!")
        print("Установите его командой: pip install streamlit")
        input("Нажмите Enter для выхода...")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        input("Нажмите Enter для выхода...")

if __name__ == "__main__":
    main()
