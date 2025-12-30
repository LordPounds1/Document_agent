@echo off
chcp 65001 >nul
title Document Processing Agent

echo ================================================
echo    📄 Document Processing Agent
echo ================================================
echo.
echo 🚀 Запуск приложения...
echo.

cd /d "%~dp0"

REM Проверяем наличие Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Python не найден! Установите Python 3.10+
    pause
    exit /b 1
)

REM Запускаем Streamlit
echo 🌐 Открытие браузера...
start "" http://localhost:8501

echo.
echo ⏳ Запуск сервера Streamlit...
echo.
echo Для остановки нажмите Ctrl+C или закройте это окно
echo ================================================
echo.

streamlit run app_streamlit.py --server.port 8501 --server.headless true

pause
