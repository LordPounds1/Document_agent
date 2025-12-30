@echo off
chcp 65001 >nul
title Создание EXE для Document Processing Agent

echo ================================================
echo    Создание EXE файла
echo ================================================
echo.

cd /d "%~dp0"

REM Проверяем PyInstaller
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo 📦 Установка PyInstaller...
    pip install pyinstaller
)

echo.
echo 🔨 Создание EXE файла...
echo.

REM Создаём exe из launcher.py
pyinstaller --onefile --windowed --name "DocumentAgent" ^
    --icon=NONE ^
    --add-data "app_streamlit.py;." ^
    --add-data "config.py;." ^
    --add-data "agents;agents" ^
    --add-data "core;core" ^
    --add-data "processors;processors" ^
    --add-data "templates;templates" ^
    --add-data "models;models" ^
    --add-data ".streamlit;.streamlit" ^
    --hidden-import streamlit ^
    --hidden-import pandas ^
    --hidden-import openpyxl ^
    launcher.py

echo.
if exist "dist\DocumentAgent.exe" (
    echo ✅ EXE файл создан: dist\DocumentAgent.exe
    echo.
    echo 📋 Для запуска:
    echo    1. Скопируйте папку dist в нужное место
    echo    2. Запустите DocumentAgent.exe
    echo.
    echo ⚠️  Важно: убедитесь что Python и Streamlit установлены в системе!
) else (
    echo ❌ Ошибка создания EXE файла
)

echo.
pause
