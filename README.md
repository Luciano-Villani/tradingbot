@'
# ArgenFunding Bot v1.0

Bot de trading funding rate arbitrage optimizado para Argentina.

## Instalación

```bash
# Clonar repo
git clone <url> C:\TradingBot
cd C:\TradingBot

# Instalar dependencias
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Configurar
copy config\.env.example config\.env
# Editar config\.env con tus API keys

# Ejecutar
.\start_bot.bat