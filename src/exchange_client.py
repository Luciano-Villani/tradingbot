import os
import ccxt
from typing import Dict, Optional
from loguru import logger
from decimal import Decimal, ROUND_DOWN

class BinanceClient:
    """Cliente Binance Futures con Demo Trading y sincronización de tiempo"""
    
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self.exchange = self._init_exchange()
        self.markets = None
        
    def _init_exchange(self) -> ccxt.binance:
        """Inicializa conexión con endpoint Demo correcto"""
        config = {
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
            },
            'timeout': 30000,
        }
        
        if self.paper_mode:
            # DEMO TRADING: endpoint oficial de Binance
            config['urls'] = {
                'api': {
                    'public': 'https://demo-fapi.binance.com/fapi/v1',
                    'private': 'https://demo-fapi.binance.com/fapi/v1',
                    'fapiPublic': 'https://demo-fapi.binance.com/fapi/v1',
                    'fapiPrivate': 'https://demo-fapi.binance.com/fapi/v1',
                    'fapiPublicV2': 'https://demo-fapi.binance.com/fapi/v2',
                    'fapiPrivateV2': 'https://demo-fapi.binance.com/fapi/v2',
                }
            }
            logger.info("📝 Conectando a Binance DEMO TRADING")
            logger.info("🔗 Endpoint: https://demo-fapi.binance.com")
        else:
            logger.warning("💰 Conectando a Binance REAL")
        
        return ccxt.binance(config)
    
    def load_markets(self) -> bool:
        """Carga mercados con sincronización previa"""
        try:
            # Sincronizar tiempo primero (evita error -1021)
            logger.info("⏱️ Sincronizando tiempo...")
            self.exchange.load_time_difference()
            
            # Cargar mercados
            self.markets = self.exchange.load_markets()
            logger.info(f"✅ {len(self.markets)} mercados cargados")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cargando mercados: {e}")
            return False
    
    def fetch_funding_rate(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Obtiene funding rate actual"""
        try:
            funding = self.exchange.fetch_funding_rate(symbol)
            return {
                'symbol': symbol,
                'fundingRate': float(funding['fundingRate']),
                'fundingTime': funding['fundingTimestamp'],
                'markPrice': float(funding['markPrice']),
                'indexPrice': float(funding.get('indexPrice', 0)),
                'nextFundingTime': funding['nextFundingTimestamp'],
                'timestamp': funding['timestamp']
            }
        except Exception as e:
            logger.error(f"❌ Error funding: {e}")
            return None
    
    def fetch_ticker(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Ticker actual"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'symbol': symbol,
                'last': float(ticker['last']),
                'bid': float(ticker['bid']),
                'ask': float(ticker['ask']),
                'spread': float(ticker['ask'] - ticker['bid']),
                'volume': float(ticker['quoteVolume']),
                'timestamp': ticker['timestamp']
            }
        except Exception as e:
            logger.error(f"❌ Error ticker: {e}")
            return None
    
    def fetch_balance(self) -> Optional[Dict]:
        """Balance USDT"""
        try:
            # Paper sin API keys válidas = balance simulado
            if self.paper_mode:
                api_key = os.getenv('BINANCE_API_KEY', '')
                if not api_key or api_key == 'tu_api_key_aqui':
                    logger.info("📝 Balance simulado: $10,000 USDT")
                    return {'free': 10000.0, 'used': 0.0, 'total': 10000.0}
            
            # Llamada real
            balance = self.exchange.fetch_balance()
            usdt = balance.get('USDT', {})
            return {
                'free': float(usdt.get('free', 0)),
                'used': float(usdt.get('used', 0)),
                'total': float(usdt.get('total', 0))
            }
            
        except Exception as e:
            logger.error(f"❌ Error balance: {e}")
            if self.paper_mode:
                return {'free': 10000.0, 'used': 0.0, 'total': 10000.0}
            return None
    
    def create_order(self, symbol: str, side: str, amount: float, 
                     price: float = None, order_type: str = 'limit',
                     params: Dict = None) -> Optional[Dict]:
        """Crear orden"""
        if self.paper_mode:
            # Verificar si tenemos API keys válidas
            api_key = os.getenv('BINANCE_API_KEY', '')
            if not api_key or api_key == 'tu_api_key_aqui':
                return self._paper_order(symbol, side, amount, price, order_type)
        
        try:
            amount = self._round_amount(symbol, amount)
            order = self.exchange.create_order(
                symbol=symbol,
                type=order_type,
                side=side,
                amount=amount,
                price=price,
                params=params or {}
            )
            logger.info(f"✅ Orden: {order['id']} | {side} {amount} @ {price}")
            return order
            
        except Exception as e:
            logger.error(f"❌ Error orden: {e}")
            return None
    
    def _paper_order(self, symbol: str, side: str, amount: float,
                     price: float, order_type: str) -> Dict:
        """Orden simulada para paper sin API"""
        order_id = f"paper_{int(__import__('time').time() * 1000)}"
        logger.info(f"📝 [PAPER] {side}: {amount} {symbol} @ {price}")
        return {
            'id': order_id,
            'status': 'filled',  # Simular ejecución inmediata
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'price': price,
            'type': order_type,
            'filled': amount,
            'remaining': 0
        }
    
    def _round_amount(self, symbol: str, amount: float) -> float:
        """Redondea a precisión del mercado"""
        if not self.markets or symbol not in self.markets:
            return amount
        precision = self.markets[symbol].get('precision', {}).get('amount', 8)
        quanto = Decimal(10) ** -precision
        rounded = Decimal(str(amount)).quantize(quanto, rounding=ROUND_DOWN)
        return float(rounded)
    
    def close_position(self, symbol: str = 'BTC/USDT') -> bool:
        """Cierra posición"""
        try:
            # Paper sin API = simular cierre
            if self.paper_mode:
                api_key = os.getenv('BINANCE_API_KEY', '')
                if not api_key or api_key == 'tu_api_key_aqui':
                    logger.info("📝 [PAPER] Posición cerrada (simulado)")
                    return True
            
            positions = self.exchange.fetch_positions([symbol])
            for pos in positions:
                contracts = float(pos.get('contracts', 0))
                if contracts != 0:
                    side = 'sell' if pos['side'] == 'long' else 'buy'
                    self.exchange.create_market_order(symbol, side, abs(contracts))
                    logger.info(f"✅ Cerrado: {pos['side']} {contracts}")
                    return True
            
            logger.info("📭 No hay posición")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error cerrando: {e}")
            return False
    
    def get_position(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Obtiene posición actual"""
        try:
            # Paper sin API = simular sin posición
            if self.paper_mode:
                api_key = os.getenv('BINANCE_API_KEY', '')
                if not api_key or api_key == 'tu_api_key_aqui':
                    return None
            
            positions = self.exchange.fetch_positions([symbol])
            for pos in positions:
                if float(pos.get('contracts', 0)) != 0:
                    return {
                        'side': pos['side'],
                        'size': float(pos['contracts']),
                        'entryPrice': float(pos['entryPrice']),
                        'markPrice': float(pos['markPrice']),
                        'pnl': float(pos['unrealizedPnl']),
                        'leverage': float(pos['leverage'])
                    }
            return None
        except Exception as e:
            logger.error(f"❌ Error posición: {e}")
            return None
        