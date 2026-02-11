@echo off
chcp 65001 >nul
title ArgenFunding Bot - v1.1 Demo Trading

cd /d C:\tradingbot

if not exist venv (
    echo ========================================
    echo  Creando entorno virtual...
    echo ========================================
    python -m venv venv
    echo.
)

call venv\Scripts\activate

if not exist venv\Lib\site-packages\ccxt (
    echo ========================================
    echo  Instalando dependencias...
    echo ========================================
    pip install -r requirements.txt
    echo.
)

:menu
cls
echo ========================================
echo   ARGENFUNDING BOT v1.1
echo   Demo Trading Edition
echo ========================================
echo.
echo  MODO ACTUAL:
type config\.env | findstr "PAPER_MODE"
echo.
echo  [1] Iniciar Bot (DEMO TRADING)
echo  [2] Iniciar Bot (REAL - CUIDADO)
echo  [3] Test de Latencia (Ping)
echo  [4] Test de Latencia (API)
echo  [5] Test WebSocket
echo  [6] Ver Logs
echo  [7] Editar configuracion (.env)
echo  [8] Actualizar desde GitHub
echo  [9] Salir
echo.
set /p opcion="Selecciona opcion (1-9): "

if "%opcion%"=="1" goto demo
if "%opcion%"=="2" goto real
if "%opcion%"=="3" goto test_ping
if "%opcion%"=="4" goto test_api
if "%opcion%"=="5" goto test_ws
if "%opcion%"=="6" goto logs
if "%opcion%"=="7" goto config
if "%opcion%"=="8" goto update
if "%opcion%"=="9" goto fin
goto menu

:demo
cls
echo ========================================
echo  MODO DEMO TRADING
echo ========================================
echo.
echo Verificando configuracion...
type config\.env | findstr "BINANCE_API_KEY" | findstr /V "tu_api_key" >nul
if errorlevel 1 (
    echo ⚠️  ADVERTENCIA: Parece que no tienes API keys configuradas
    echo.
    echo Para usar Demo Trading necesitas:
    echo 1. Ir a Binance -^> Futures -^> Demo Trading
    echo 2. Generar API keys en el modo Demo
    echo 3. Editar config\.env con tus keys
    echo.
    pause
    goto menu
)

echo ✅ API keys detectadas
echo 📝 Conectando a Binance DEMO TRADING...
echo.
set PAPER_MODE=true
python src/main.py
pause
goto menu

:real
cls
echo ========================================
echo  MODO REAL - DINERO REAL EN JUEGO
echo ========================================
echo.
echo ⚠️  ESTAS POR OPERAR CON DINERO REAL
echo.
echo Estas seguro? Escribe 'OPERAR_REAL' para confirmar:
set /p confirm="Confirmacion: "
if /I not "%confirm%"=="OPERAR_REAL" (
    echo Cancelado.
    timeout /t 2 >nul
    goto menu
)

echo.
echo 💰 Iniciando en MODO REAL...
echo.
set PAPER_MODE=false
python src/main.py
pause
goto menu

:test_ping
cls
echo ========================================
echo  TEST DE LATENCIA - Ping ICMP
echo ========================================
echo.
python tests/test_latency_ping.py
goto menu

:test_api
cls
echo ========================================
echo  TEST DE LATENCIA - API REST
echo ========================================
echo.
python tests/test_latency_api.py
goto menu

:test_ws
cls
echo ========================================
echo  TEST DE LATENCIA - WebSocket
echo ========================================
echo.
python tests/test_websocket.py
goto menu

:logs
cls
echo ========================================
echo  Abriendo directorio de logs...
echo ========================================
start data\logs
goto menu

:config
cls
echo ========================================
echo  Editando configuracion...
echo ========================================
notepad config\.env
echo.
echo Configuracion guardada. Reinicia el bot para aplicar cambios.
pause
goto menu

:update
cls
echo ========================================
echo  Actualizando desde GitHub...
echo ========================================
echo.
git pull origin master
if errorlevel 1 (
    echo ❌ Error al actualizar
) else (
    echo ✅ Actualizado correctamente
    echo 🔄 Reinstalando dependencias...
    pip install -r requirements.txt
)
pause
goto menu

:fin
cls
echo ========================================
echo  Hasta luego!
echo ========================================
echo.
timeout /t 2 >nul
exit
