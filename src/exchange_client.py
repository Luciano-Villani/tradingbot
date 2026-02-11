import os
import ccxt
from typing import Dict, Optional
from loguru import logger
from decimal import Decimal, ROUND_DOWN

class BinanceClient:
    """Cliente Binance Futures con endpoint Demo correcto"""
    
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self.exchange = self._init_exchange()
        self.markets = None
        
    def _init_exchange(self) -> ccxt.binance:
        """Inicializa conexión"""
        
        config = {
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
            },
            'timeout': 30000,
        }
        
        exchange = ccxt.binance(config)
        
        if self.paper_mode:
            # FORZAR completamente las URLs a Futures Demo
            exchange.urls = {
                'logo': 'https://binance.com',
                'api': {
                    'public': 'https://demo-fapi.binance.com/fapi/v1',
                    'private': 'https://demo-fapi.binance.com/fapi/v1',
                    'fapiPublic': 'https://demo-fapi.binance.com/fapi/v1',
                    'fapiPrivate': 'https://demo-fapi.binance.com/fapi/v1',
                    'fapiPublicV2': 'https://demo-fapi.binance.com/fapi/v2',
                    'fapiPrivateV2': 'https://demo-fapi.binance.com/fapi/v2',
                },
                'www': 'https://www.binance.com',
                'doc': 'https://binance-docs.github.io/apidocs/spot/en',
            }
            logger.info("📝 Futures DEMO: https://demo-fapi.binance.com")
        else:
            logger.warning("💰 Futures REAL: https://fapi.binance.com")
        
        return exchange
    
    def load_markets(self) -> bool:
        """Carga mercados sin spot API"""
        try:
            logger.info("⏱️ Sincronizando tiempo...")
            
            # Sincronizar tiempo manualmente en endpoint correcto
            try:
                response = self.exchange.fetch2('time', 'fapiPublic')
                server_time = response['serverTime']
                local_time = self.exchange.milliseconds()
                self.exchange.options['timeDifference'] = server_time - local_time
                logger.info(f"✅ Tiempo sincronizado: diff={self.exchange.options['timeDifference']}ms")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo sincronizar tiempo: {e}")
            
            # Cargar mercados de futures específicamente
            logger.info("📊 Cargando mercados futures...")
            self.markets = self.exchange.fetch_markets(params={'type': 'future'})
            logger.info(f"✅ {len(self.markets)} mercados cargados")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def fetch_balance(self) -> Optional[Dict]:
        """Balance de futures"""
        try:
            # Usar endpoint de futures explícitamente
            balance = self.exchange.fetch_balance(params={'type': 'future'})
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
        """Funding rate"""
        try:
            funding = self.exchange.fetch_funding_rate(symbol)
            return {
                'symbol': symbol,
                'fundingRate': float(funding['fundingRate']),
                'markPrice': float(funding['markPrice']),
                'nextFundingTime': funding['nextFundingTimestamp'],
            }
        except Exception as e:
            logger.error(f"❌ Error funding: {e}")
            return None
    
    def fetch_ticker(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Ticker"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'last': float(ticker['last']),
                'bid': float(ticker['bid']),
                'ask': float(ticker['ask']),
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
                params={'type': 'future', **(params or {})}
            )
            logger.info(f"✅ Orden: {order['id']}")
            return order
        except Exception as e:
            logger.error(f"❌ Error orden: {e}")
            return None
    
    def _round_amount(self, symbol: str, amount: float) -> float:
        if not self.markets or symbol not in self.markets:
            return amount
        precision = self.markets[symbol].get('precision', {}).get('amount', 8)
        quanto = Decimal(10) ** -precision
        return float(Decimal(str(amount)).quantize(quanto, rounding=ROUND_DOWN))
    
    def close_position(self, symbol: str = 'BTC/USDT') -> bool:
        try:
            positions = self.exchange.fetch_positions([symbol], params={'type': 'future'})
            for pos in positions:
                contracts = float(pos.get('contracts', 0))
                if contracts != 0:
                    side = 'sell' if pos['side'] == 'long' else 'buy'
                    self.exchange.create_market_order(symbol, side, abs(contracts), params={'type': 'future'})
                    return True
            return False
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def get_position(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        try:
            positions = self.exchange.fetch_positions([symbol], params={'type': 'future'})
            for pos in positions:
                if float(pos.get('contracts', 0)) != 0:
                    return {
                        'side': pos['side'],
                        'size': float(pos['contracts']),
                        'pnl': float(pos.get('unrealizedPnl', 0)),
                    }
            return None
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return None
        