import os
import ccxt
from typing import Dict, Optional
from loguru import logger
from decimal import Decimal, ROUND_DOWN

class BinanceClient:
    """Cliente Binance Futures - Solo endpoints fapi, sin sapi"""
    
    def __init__(self, paper_mode: bool = True):
        self.paper_mode = paper_mode
        self.exchange = self._init_exchange()
        self.markets = None
        self._balance_cache = {'free': 10000.0, 'used': 0.0, 'total': 10000.0}  # Default para demo
        
    def _init_exchange(self) -> ccxt.binance:
        """Inicializa conexión"""
        
        config = {
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': False,  # Lo hacemos manual
            },
            'timeout': 30000,
        }
        
        exchange = ccxt.binance(config)
        
        if self.paper_mode:
            # SOLO endpoints fapi, nada de sapi
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
            }
            logger.info("📝 Futures DEMO: https://demo-fapi.binance.com")
        else:
            logger.warning("💰 Futures REAL")
        
        return exchange
    
    def load_markets(self) -> bool:
        """Carga mercados usando solo fapi"""
        try:
            logger.info("📊 Cargando mercados...")
            
            # Usar fetch2 para llamar directo al endpoint fapi
            response = self.exchange.fetch2('exchangeInfo', 'fapiPublic')
            
            # Parsear mercados manualmente
            markets = {}
            for symbol_data in response.get('symbols', []):
                if symbol_data.get('status') == 'TRADING':
                    symbol = symbol_data['symbol']
                    markets[symbol] = {
                        'symbol': symbol,
                        'base': symbol_data['baseAsset'],
                        'quote': symbol_data['quoteAsset'],
                        'precision': {
                            'amount': symbol_data.get('quantityPrecision', 8),
                            'price': symbol_data.get('pricePrecision', 8),
                        }
                    }
            
            self.markets = markets
            logger.info(f"✅ {len(markets)} mercados cargados")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error: {e}")
            return False
    
    def fetch_balance(self) -> Optional[Dict]:
        """Balance usando fapi directo"""
        try:
            # Llamar a fapi/v2/account directamente
            response = self.exchange.fetch2('account', 'fapiPrivateV2')
            
            # Buscar USDT en assets
            assets = response.get('assets', [])
            usdt_asset = next((a for a in assets if a.get('asset') == 'USDT'), None)
            
            if usdt_asset:
                balance = {
                    'free': float(usdt_asset.get('availableBalance', 0)),
                    'used': float(usdt_asset.get('initialMargin', 0)),
                    'total': float(usdt_asset.get('walletBalance', 0))
                }
                self._balance_cache = balance
                return balance
            else:
                logger.warning("⚠️ No se encontró USDT en balance")
                return self._balance_cache
                
        except Exception as e:
            logger.error(f"❌ Error balance: {e}")
            # En demo, usar cache si falla
            if self.paper_mode:
                logger.info("📝 Usando balance demo cacheado")
                return self._balance_cache
            return None
    
    def fetch_funding_rate(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Funding rate"""
        try:
            # Convertir BTC/USDT a BTCUSDT para fapi
            symbol_fapi = symbol.replace('/', '')
            
            response = self.exchange.fetch2('premiumIndex', 'fapiPublic', 'GET', {'symbol': symbol_fapi})
            
            return {
                'symbol': symbol,
                'fundingRate': float(response.get('lastFundingRate', 0)),
                'markPrice': float(response.get('markPrice', 0)),
                'nextFundingTime': response.get('nextFundingTime'),
            }
        except Exception as e:
            logger.error(f"❌ Error funding: {e}")
            return None
    
    def fetch_ticker(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Ticker"""
        try:
            symbol_fapi = symbol.replace('/', '')
            response = self.exchange.fetch2('ticker/24hr', 'fapiPublic', 'GET', {'symbol': symbol_fapi})
            
            return {
                'last': float(response.get('lastPrice', 0)),
                'bid': float(response.get('bidPrice', 0)),
                'ask': float(response.get('askPrice', 0)),
                'volume': float(response.get('quoteVolume', 0)),
            }
        except Exception as e:
            logger.error(f"❌ Error ticker: {e}")
            return None
    
    def create_order(self, symbol: str, side: str, amount: float, 
                     price: float = None, order_type: str = 'limit') -> Optional[Dict]:
        """Crear orden"""
        try:
            symbol_fapi = symbol.replace('/', '')
            
            params = {
                'symbol': symbol_fapi,
                'side': side.upper(),
                'type': order_type.upper(),
                'quantity': self._round_amount(symbol, amount),
            }
            
            if order_type == 'limit':
                params['price'] = price
                params['timeInForce'] = 'GTC'
            
            response = self.exchange.fetch2('order', 'fapiPrivate', 'POST', params)
            
            logger.info(f"✅ Orden creada: {response.get('orderId')}")
            return {
                'id': response.get('orderId'),
                'status': response.get('status'),
            }
        except Exception as e:
            logger.error(f"❌ Error orden: {e}")
            return None
    
    def _round_amount(self, symbol: str, amount: float) -> float:
        """Redondea según precisión del mercado"""
        if not self.markets or symbol not in self.markets:
            return round(amount, 3)
        
        precision = self.markets[symbol].get('precision', {}).get('amount', 3)
        quanto = Decimal(10) ** -precision
        return float(Decimal(str(amount)).quantize(quanto, rounding=ROUND_DOWN))
    
    def close_position(self, symbol: str = 'BTC/USDT') -> bool:
        """Cerrar posición"""
        try:
            # Obtener posición abierta
            symbol_fapi = symbol.replace('/', '')
            response = self.exchange.fetch2('positionRisk', 'fapiPrivate', 'GET', {'symbol': symbol_fapi})
            
            positions = response if isinstance(response, list) else [response]
            
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
                    # Cerrar con orden market opuesta
                    side = 'SELL' if position_amt > 0 else 'BUY'
                    
                    self.exchange.fetch2('order', 'fapiPrivate', 'POST', {
                        'symbol': symbol_fapi,
                        'side': side,
                        'type': 'MARKET',
                        'quantity': abs(position_amt),
                        'reduceOnly': 'true'
                    })
                    logger.info(f"✅ Posición cerrada: {symbol}")
                    return True
            
            logger.info("📭 No hay posición para cerrar")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error cerrando: {e}")
            return False
    
    def get_position(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Obtener posición actual"""
        try:
            symbol_fapi = symbol.replace('/', '')
            response = self.exchange.fetch2('positionRisk', 'fapiPrivate', 'GET', {'symbol': symbol_fapi})
            
            positions = response if isinstance(response, list) else [response]
            
            for pos in positions:
                amt = float(pos.get('positionAmt', 0))
                if amt != 0:
                    return {
                        'side': 'long' if amt > 0 else 'short',
                        'size': abs(amt),
                        'entryPrice': float(pos.get('entryPrice', 0)),
                        'markPrice': float(pos.get('markPrice', 0)),
                        'pnl': float(pos.get('unRealizedProfit', 0)),
                    }
            return None
            
        except Exception as e:
            logger.error(f"❌ Error posición: {e}")
            return None
        