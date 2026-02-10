@echo off
chcp 65001 >nul
title ArgenFunding Bot

cd /d C:\TradingBot

if not exist venv (
    echo Creando entorno virtual...
    python -m venv venv
)

call venv\Scripts\activate

if not exist venv\Lib\site-packages\ccxt (
    echo Instalando dependencias...
    pip install -r requirements.txt
)

:menu
cls
echo ========================================
echo   ARGENFUNDING BOT v1.0
echo ========================================
echo.
echo  [1] Iniciar Bot (PAPER MODE)
echo  [2] Iniciar Bot (REAL)
echo  [3] Test Ping
echo  [4] Test API
echo  [5] Test WebSocket
echo  [6] Ver Logs
echo  [7] Salir
echo.
set /p opcion="Selecciona (1-7): "

if "%opcion%"=="1" goto paper
if "%opcion%"=="2" goto real
if "%opcion%"=="3" goto test_ping
if "%opcion%"=="4" goto test_api
if "%opcion%"=="5" goto test_ws
if "%opcion%"=="6" goto logs
if "%opcion%"=="7" goto fin
goto menu

:paper
python src/main.py
pause
goto menu

:real
echo.
set /p confirm="Escribe 'REAL' para confirmar: "
if /I "%confirm%"=="REAL" (
    set PAPER_MODE=false
    python src/main.py
)
goto menu

:test_ping
python tests/test_latency_ping.py
goto menu

:test_api
python tests/test_latency_api.py
goto menu

:test_ws
python tests/test_websocket.py
goto menu

:logs
start data\logs
goto menu

:fin
exit
