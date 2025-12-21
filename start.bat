@echo off
title Trading Bot - Sistema Autonomo
cd /d "%~dp0"
color 0A

:MENU
cls
echo.
echo  ╔════════════════════════════════════════════════╗
echo  ║     🚀 TRADING BOT - SISTEMA AUTONOMO 🚀      ║
echo  ╠════════════════════════════════════════════════╣
echo  ║                                                ║
echo  ║   [1] Iniciar TODO (MT5 + Dashboard + Bot)    ║
echo  ║   [2] Solo Dashboard                          ║
echo  ║   [3] Solo Bot (requiere MT5 abierto)         ║
echo  ║   [4] Salir                                   ║
echo  ║                                                ║
echo  ╚════════════════════════════════════════════════╝
echo.
set /p option=Selecciona una opcion (1-4): 

if "%option%"=="1" goto ALL
if "%option%"=="2" goto DASHBOARD
if "%option%"=="3" goto BOT
if "%option%"=="4" exit
goto MENU

:ALL
cls
echo.
echo [1/4] Abriendo MetaTrader 5...
start "" "C:\Program Files\Admirals Group MT5 Terminal\terminal64.exe"
echo.
echo [2/4] Esperando 5 segundos para que MT5 inicie...
timeout /t 5 /nobreak >nul
echo.
echo [3/4] Iniciando Dashboard en segundo plano...
start "Dashboard" cmd /c "cd /d "%~dp0" && call venv\Scripts\activate.bat && start "" http://localhost:8501 && venv\Scripts\streamlit.exe run ui/dashboard.py"
echo.
echo [4/4] Esperando 3 segundos...
timeout /t 3 /nobreak >nul
echo.
echo [OK] Iniciando Bot de Trading...
call venv\Scripts\activate.bat
python run.py
pause
goto MENU

:DASHBOARD
cls
echo.
echo Iniciando Dashboard de Trading...
echo.
call venv\Scripts\activate.bat
start "" http://localhost:8501
venv\Scripts\streamlit.exe run ui/dashboard.py
pause
goto MENU

:BOT
cls
echo.
echo [!] Asegurate de tener MetaTrader 5 abierto
echo     con tu cuenta demo antes de continuar.
echo.
pause
echo.
echo Iniciando bot de trading...
call venv\Scripts\activate.bat
python run.py
pause
goto MENU
