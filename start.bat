@echo off
title ARAFURA - Trading Bot Launcher
cd /d "%~dp0"

:: Verificar si el venv existe
if not exist "venv\Scripts\activate.bat" (
    echo [!] Error: No se encontro el entorno virtual en \venv
    pause
    exit
)

:: Lanzar el menu premium en Python
call venv\Scripts\activate.bat
python launcher.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] El lanzador se cerro con errores.
    pause
)
