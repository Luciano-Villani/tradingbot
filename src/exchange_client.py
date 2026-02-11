import os
import ccxt
from typing import Dict, Optional
from loguru import logger

class BinanceClient:
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self.exchange = self._init_exchange()
        self.markets = None
        self._balance_cache = {'USDT': 0.0, 'USDC': 0.0, 'BTC': 0.0}
        
    def _init_exchange(self) -> ccxt.binance:
        config = {
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        }
        
        exchange = ccxt.binance(config)
        
        if self.paper_mode:
            # Nueva configuración para Demo Trading (reemplaza a Sandbox/Testnet)
            exchange.urls['api']['fapiPublic'] = 'https://demo-fapi.binance.com/fapi/v1'
            exchange.urls['api']['fapiPrivate'] = 'https://demo-fapi.binance.com/fapi/v1'
            logger.info("🧪 MODO DEMO TRADING ACTIVADO (Nueva URL)")
        else:
            logger.warning("💰 MODO REAL ACTIVADO")
            
        return exchange
    
    def load_markets(self) -> bool:
        try:
            # Forzamos la carga desde la API
            self.markets = self.exchange.load_markets(True)
            logger.info(f"✅ {len(self.markets)} mercados cargados")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando mercados: {e}")
            return False
    
    def fetch_balance(self) -> Optional[Dict]:
        try:
            # Usamos el método unificado de ccxt
            balance = self.exchange.fetch_balance()
            
            # Binance Futures guarda el balance en 'total' dentro de cada asset
            res = {
                'USDT': {'free': balance.get('USDT', {}).get('free', 0.0), 'total': balance.get('USDT', {}).get('total', 0.0)},
                'USDC': {'free': balance.get('USDC', {}).get('free', 0.0), 'total': balance.get('USDC', {}).get('total', 0.0)},
                'BTC': {'free': balance.get('BTC', {}).get('free', 0.0), 'total': balance.get('BTC', {}).get('total', 0.0)},
            }
            
            self._balance_cache = {k: v['free'] for k, v in res.items()}
            return res
        except Exception as e:
            # Si el error es por la API Key en modo Demo, mostramos un aviso claro
            if "API-key format" in str(e):
                logger.error("❌ Error: Tu API Key no es válida para Demo Trading. Generá una en la sección 'Demo Trading' de Binance Futures.")
            else:
                logger.error(f"❌ Error balance: {e}")
            return None

    def create_order(self, symbol: str, side: str, amount: float, price: float = None, order_type: str = 'market') -> Optional[Dict]:
        try:
            if not self.markets:
                self.load_markets()

            # Redondeo infalible de CCXT
            amount_prec = self.exchange.amount_to_precision(symbol, amount)
            
            if order_type.lower() == 'limit':
                price_prec = self.exchange.price_to_precision(symbol, price)
                order = self.exchange.create_order(symbol, 'limit', side, amount_prec, price_prec)
            else:
                order = self.exchange.create_order(symbol, 'market', side, amount_prec)

            logger.info(f"✅ Orden {side} exitosa en {symbol}: ID {order['id']}")
            return {'id': order['id'], 'status': order['status']}
        except Exception as e:
            logger.error(f"❌ Error en orden {symbol}: {e}")
            return None

    def fetch_funding_rate(self, symbol: str) -> Optional[Dict]:
        try:
            # ccxt maneja la conversión a fapi internamente
            funding = self.exchange.fetch_funding_rate(symbol)
            return {
                'symbol': symbol,
                'fundingRate': funding.get('fundingRate', 0.0),
                'markPrice': funding.get('markPrice', 0.0),
                'nextFundingTime': funding.get('info', {}).get('nextFundingTime'),
            }
        except Exception as e:
            logger.error(f"❌ Error funding {symbol}: {e}")
            return None

    def fetch_ticker(self, symbol: str) -> Optional[Dict]:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'last': ticker.get('last', 0.0),
                'bid': ticker.get('bid', 0.0),
                'ask': ticker.get('ask', 0.0)
            }
        except Exception as e:
            logger.error(f"❌ Error ticker {symbol}: {e}")
            return None

    def close_position(self, symbol: str) -> bool:
        try:
            # Obtenemos posiciones abiertas
            positions = self.exchange.fetch_positions([symbol])
            for pos in positions:
                amt = float(pos.get('contracts', 0))
                if amt != 0:
                    # Lógica inversa para cerrar
                    side = 'sell' if amt > 0 else 'buy'
                    self.exchange.create_order(symbol, 'market', side, abs(amt), params={'reduceOnly': True})
                    logger.info(f"✅ Posición cerrada en {symbol}")
                    return True
            return False
        except Exception as e:
            logger.error(f"❌ Error cerrando {symbol}: {e}")
            return False