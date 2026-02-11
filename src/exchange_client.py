import os
import ccxt
from typing import Dict, Optional
from loguru import logger
from decimal import Decimal, ROUND_DOWN

class BinanceClient:
    """Cliente Binance Futures - Demo usa endpoint de producción con keys de Demo"""
    
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self.exchange = self._init_exchange()
        self.markets = None
        
    def _init_exchange(self) -> ccxt.binance:
        """Inicializa conexión"""
        
        # IMPORTANTE: Las keys de Demo funcionan en el endpoint de producción
        # No es necesario cambiar URLs, solo usar las keys correctas
        
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
            logger.info("📝 Conectando a Binance DEMO (usa endpoint producción con keys de Demo)")
        else:
            logger.warning("💰 Conectando a Binance REAL")
        
        return ccxt.binance(config)
    
    def load_markets(self) -> bool:
        """Carga mercados"""
        try:
            # Sincronizar tiempo primero
            logger.info("⏱️ Sincronizando tiempo...")
            self.exchange.load_time_difference()
            
            # Cargar mercados
            self.markets = self.exchange.load_markets()
            logger.info(f"✅ {len(self.markets)} mercados cargados")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cargando mercados: {e}")
            # Si falla por keys, mostrar mensaje útil
            if "Invalid Api-Key" in str(e):
                logger.error("🔑 Las API keys no son válidas para este modo")
                logger.error("   Si usás Demo, asegurate de generar las keys DENTRO del modo Demo de Binance")
            return False
    
    def fetch_balance(self) -> Optional[Dict]:
        """Balance USDT"""
        try:
            balance = self.exchange.fetch_balance()
            usdt = balance.get('USDT', {})
            return {
                'free': float(usdt.get('free', 0)),
                'used': float(usdt.get('used', 0)),
                'total': float(usdt.get('total', 0))
            }
        except Exception as e:
            logger.error(f"❌ Error balance: {e}")
            return None
    
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
    
    def create_order(self, symbol: str, side: str, amount: float, 
                     price: float = None, order_type: str = 'limit',
                     params: Dict = None) -> Optional[Dict]:
        """Crear orden"""
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
        