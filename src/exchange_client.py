import os
import ccxt
from typing import Dict, Optional
from loguru import logger
from decimal import Decimal, ROUND_DOWN
import time

class BinanceClient:
    """Cliente Binance Futures - Solo FAPI, sin SAPI"""
    
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self.exchange = self._init_exchange()
        self.markets = None
        
    def _init_exchange(self) -> ccxt.binance:
        """Inicializa conexión puramente FAPI"""
        
        config = {
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                # Desactivar llamadas a sapi
                'fetchCurrencies': False,
                'fetchMarkets': 'futures',
            },
            'timeout': 30000,
        }
        
        exchange = ccxt.binance(config)
        
        if self.paper_mode:
            # REEMPLAZAR completamente las URLs, no solo api
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
                'doc': 'https://binance-docs.github.io/apidocs/futures/en/',
            }
            logger.info("📝 Futures DEMO: https://demo-fapi.binance.com")
        else:
            logger.warning("💰 Futures REAL: https://fapi.binance.com")
        
        return exchange
    
    def load_markets(self) -> bool:
        """Carga mercados SOLO de futures, sin sapi"""
        try:
            logger.info("⏱️ Sincronizando tiempo...")
            
            # Sincronizar tiempo vía fapi
            try:
                response = self.exchange.fapiPublicGetTime()
                server_time = response['serverTime']
                local_time = int(time.time() * 1000)
                self.exchange.options['timeDifference'] = server_time - local_time
                logger.info(f"✅ Tiempo sync: {self.exchange.options['timeDifference']}ms")
            except Exception as e:
                logger.warning(f"⚠️ Time sync: {e}")
            
            # Cargar mercados manualmente desde fapi
            logger.info("📊 Cargando mercados de fapi...")
            
            # Llamada directa a fapi sin pasar por load_markets de ccxt
            exchange_info = self.exchange.fapiPublicGetExchangeInfo()
            
            # Parsear mercados manualmente
            self.markets = {}
            for symbol_info in exchange_info.get('symbols', []):
                if symbol_info.get('status') == 'TRADING':
                    symbol = symbol_info['symbol']
                    base = symbol_info['baseAsset']
                    quote = symbol_info['quoteAsset']
                    market_symbol = f"{base}/{quote}:{quote}"  # formato futures
                    
                    self.markets[market_symbol] = {
                        'id': symbol,
                        'symbol': market_symbol,
                        'base': base,
                        'quote': quote,
                        'active': True,
                        'precision': {
                            'amount': symbol_info.get('quantityPrecision', 8),
                            'price': symbol_info.get('pricePrecision', 8),
                        },
                        'limits': {
                            'amount': {'min': None, 'max': None},
                            'price': {'min': None, 'max': None},
                        },
                        'type': 'future',
                    }
            
            logger.info(f"✅ {len(self.markets)} mercados cargados")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def fetch_balance(self) -> Optional[Dict]:
        """Balance de futures vía fapi únicamente"""
        try:
            logger.info("💰 Consultando balance futures...")
            
            # Llamada directa a fapi private
            account = self.exchange.fapiPrivateGetAccount()
            
            # Buscar USDT en assets
            for asset in account.get('assets', []):
                if asset['asset'] == 'USDT':
                    return {
                        'free': float(asset.get('availableBalance', 0)),
                        'used': float(asset.get('initialMargin', 0)),
                        'total': float(asset.get('walletBalance', 0))
                    }
            
            # Si no hay USDT, retornar 0
            return {'free': 0, 'used': 0, 'total': 0}
            
        except Exception as e:
            logger.error(f"❌ Error balance: {e}")
            return None
    
    def fetch_funding_rate(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Funding rate vía fapi"""
        try:
            # Convertir BTC/USDT a BTCUSDT
            symbol_fapi = symbol.replace('/', '').replace(':USDT', '')
            
            funding = self.exchange.fapiPublicGetPremiumIndex({'symbol': symbol_fapi})
            
            return {
                'symbol': symbol,
                'fundingRate': float(funding.get('lastFundingRate', 0)),
                'markPrice': float(funding.get('markPrice', 0)),
                'indexPrice': float(funding.get('indexPrice', 0)),
                'nextFundingTime': funding.get('nextFundingTime', 0),
            }
        except Exception as e:
            logger.error(f"❌ Error funding: {e}")
            return None
    
    def fetch_ticker(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Ticker vía fapi"""
        try:
            symbol_fapi = symbol.replace('/', '').replace(':USDT', '')
            ticker = self.exchange.fapiPublicGetTickerBookTicker({'symbol': symbol_fapi})
            
            return {
                'symbol': symbol,
                'bid': float(ticker.get('bidPrice', 0)),
                'ask': float(ticker.get('askPrice', 0)),
                'last': float(ticker.get('lastPrice', 0)),
            }
        except Exception as e:
            logger.error(f"❌ Error ticker: {e}")
            return None
    
    def create_order(self, symbol: str, side: str, amount: float, 
                     price: float = None, order_type: str = 'limit',
                     params: Dict = None) -> Optional[Dict]:
        """Crear orden vía fapi"""
        try:
            symbol_fapi = symbol.replace('/', '').replace(':USDT', '')
            
            # Redondear cantidad
            amount = self._round_amount(symbol, amount)
            
            order_params = {
                'symbol': symbol_fapi,
                'side': side.upper(),
                'type': order_type.upper(),
                'quantity': amount,
            }
            
            if price and order_type.lower() == 'limit':
                order_params['price'] = price
                order_params['timeInForce'] = 'GTC'
            
            order = self.exchange.fapiPrivatePostOrder(order_params)
            
            logger.info(f"✅ Orden creada: {order.get('orderId')}")
            return {
                'id': str(order.get('orderId')),
                'status': order.get('status', 'NEW'),
            }
            
        except Exception as e:
            logger.error(f"❌ Error orden: {e}")
            return None
    
    def _round_amount(self, symbol: str, amount: float) -> float:
        """Redondea a precisión del mercado"""
        if not self.markets or symbol not in self.markets:
            return round(amount, 3)
        
        precision = self.markets[symbol].get('precision', {}).get('amount', 3)
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
        