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
            'options': {'defaultType': 'future'}
        }
        exchange = ccxt.binance(config)
        if self.paper_mode:
            exchange.set_sandbox_mode(True)
            logger.info("🧪 MODO TESTNET ACTIVADO")
        return exchange
    
    def load_markets(self) -> bool:
        """Carga mercados y sus precisiones"""
        try:
            self.markets = self.exchange.load_markets()
            logger.info(f"✅ {len(self.markets)} mercados cargados")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando mercados: {e}")
            return False
    
    def fetch_balance(self) -> Optional[Dict]:
        try:
            balance = self.exchange.fetch_balance()
            res = {
                'USDT': {'free': balance.get('USDT', {}).get('free', 0), 'total': balance.get('USDT', {}).get('total', 0)},
                'USDC': {'free': balance.get('USDC', {}).get('free', 0), 'total': balance.get('USDC', {}).get('total', 0)},
                'BTC': {'free': balance.get('BTC', {}).get('free', 0), 'total': balance.get('BTC', {}).get('total', 0)},
            }
            self._balance_cache = {k: v['free'] for k, v in res.items()}
            return res
        except Exception as e:
            logger.error(f"❌ Error balance: {e}")
            return None

    def create_order(self, symbol: str, side: str, amount: float, price: float = None, order_type: str = 'market') -> Optional[Dict]:
        try:
            # Asegurarnos de tener los mercados cargados para la precisión
            if not self.markets:
                self.load_markets()

            # Usamos las funciones de redondeo nativas de ccxt que son infalibles
            amount_prec = self.exchange.amount_to_precision(symbol, amount)
            
            params = {}
            if order_type.lower() == 'limit':
                price_prec = self.exchange.price_to_precision(symbol, price)
                order = self.exchange.create_order(symbol, 'limit', side, amount_prec, price_prec)
            else:
                # Recomendado para Funding: MARKET
                order = self.exchange.create_order(symbol, 'market', side, amount_prec)

            logger.info(f"✅ Orden {side} exitosa en {symbol}: ID {order['id']}")
            return {'id': order['id'], 'status': order['status']}
        except Exception as e:
            logger.error(f"❌ Error en orden {symbol}: {e}")
            return None

    def fetch_funding_rate(self, symbol: str) -> Optional[Dict]:
        try:
            funding = self.exchange.fetch_funding_rate(symbol)
            return {
                'symbol': symbol,
                'fundingRate': funding['fundingRate'],
                'markPrice': funding['markPrice'],
                'nextFundingTime': funding['info'].get('nextFundingTime'),
            }
        except Exception as e:
            logger.error(f"❌ Error funding {symbol}: {e}")
            return None

    def fetch_ticker(self, symbol: str) -> Optional[Dict]:
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {'last': ticker['last'], 'bid': ticker['bid'], 'ask': ticker['ask']}
        except Exception as e:
            logger.error(f"❌ Error ticker {symbol}: {e}")
            return None

    def close_position(self, symbol: str) -> bool:
        try:
            positions = self.exchange.fetch_positions([symbol])
            for pos in positions:
                amt = float(pos['contracts'])
                if amt != 0:
                    side = 'sell' if pos['side'] == 'long' else 'buy'
                    self.exchange.create_order(symbol, 'market', side, amt, params={'reduceOnly': True})
                    logger.info(f"✅ Posición cerrada en {symbol}")
                    return True
            return False
        except Exception as e:
            logger.error(f"❌ Error cerrando {symbol}: {e}")
            return False