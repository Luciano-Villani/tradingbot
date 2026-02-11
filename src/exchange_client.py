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
        self._balance_cache = {'USDT': 5000.0, 'USDC': 5000.0, 'BTC': 0.01}
        
    def _init_exchange(self) -> ccxt.binance:
        """Inicializa conexión"""
        
        config = {
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': False,
            },
            'timeout': 30000,
        }
        
        exchange = ccxt.binance(config)
        
        if self.paper_mode:
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
            response = self.exchange.fetch2('exchangeInfo', 'fapiPublic')
            
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
        """Balance completo de futures"""
        try:
            response = self.exchange.fetch2('account', 'fapiPrivateV2')
            
            assets = response.get('assets', [])
            balance = {
                'USDT': {'free': 0, 'used': 0, 'total': 0},
                'USDC': {'free': 0, 'used': 0, 'total': 0},
                'BTC': {'free': 0, 'used': 0, 'total': 0},
            }
            
            for asset in assets:
                asset_name = asset.get('asset', '')
                if asset_name in balance:
                    available = float(asset.get('availableBalance', 0))
                    wallet = float(asset.get('walletBalance', 0))
                    balance[asset_name] = {
                        'free': available,
                        'used': wallet - available,
                        'total': wallet
                    }
            
            # Actualizar cache
            self._balance_cache = {
                'USDT': balance['USDT']['free'],
                'USDC': balance['USDC']['free'],
                'BTC': balance['BTC']['free'],
            }
            
            return balance
                
        except Exception as e:
            logger.error(f"❌ Error balance: {e}")
            if self.paper_mode:
                return {
                    'USDT': {'free': self._balance_cache['USDT'], 'used': 0, 'total': self._balance_cache['USDT']},
                    'USDC': {'free': self._balance_cache['USDC'], 'used': 0, 'total': self._balance_cache['USDC']},
                    'BTC': {'free': self._balance_cache['BTC'], 'used': 0, 'total': self._balance_cache['BTC']},
                }
            return None
    
    def fetch_balance_simple(self) -> Dict:
        """Versión simplificada para dashboard"""
        balance = self.fetch_balance()
        if not balance:
            return self._balance_cache
        
        return {
            'USDT': balance.get('USDT', {}).get('free', 0),
            'USDC': balance.get('USDC', {}).get('free', 0),
            'BTC': balance.get('BTC', {}).get('free', 0),
        }
    
    def fetch_funding_rate(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
        """Funding rate"""
        try:
            symbol_fapi = symbol.replace('/', '')
            response = self.exchange.fetch2('premiumIndex', 'fapiPublic', 'GET', {'symbol': symbol_fapi})
            
            return {
                'symbol': symbol,
                'fundingRate': float(response.get('lastFundingRate', 0)),
                'markPrice': float(response.get('markPrice', 0)),
                'nextFundingTime': response.get('nextFundingTime'),
            }
        except Exception as e:
            logger.error(f"❌ Error funding {symbol}: {e}")
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
            logger.error(f"❌ Error ticker {symbol}: {e}")
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
        """Redondea según precisión del mercado asegurando tipos numéricos"""
        try:
            symbol_key = symbol.replace('/', '')
            
            # 1. Si no hay datos, un redondeo genérico seguro
            if not self.markets or symbol_key not in self.markets:
                return round(float(amount), 2)
            
            # 2. Forzamos que precision sea un entero (esto evita el error 'str')
            raw_precision = self.markets[symbol_key].get('precision', {}).get('amount', 3)
            precision = int(raw_precision) 
            
            # 3. Redondeo usando formateo de string (el método más compatible con Binance)
            # Esto elimina errores de precisión de coma flotante de Python
            format_str = f"{{:.{precision}f}}"
            rounded_str = format_str.format(amount)
            
            # 4. Validamos que el resultado sea mayor a cero para evitar error -4003
            final_amount = float(rounded_str)
            if final_amount <= 0:
                logger.warning(f"⚠️ Cantidad calculada para {symbol} es 0 tras redondeo.")
                
            return final_amount
            
        except Exception as e:
            logger.error(f"⚠️ Error crítico en redondeo para {symbol}: {e}")
            return round(float(amount), 2)
    
    def close_position(self, symbol: str = 'BTC/USDT') -> bool:
        """Cerrar posición"""
        try:
            symbol_fapi = symbol.replace('/', '')
            response = self.exchange.fetch2('positionRisk', 'fapiPrivate', 'GET', {'symbol': symbol_fapi})
            
            positions = response if isinstance(response, list) else [response]
            
            for pos in positions:
                position_amt = float(pos.get('positionAmt', 0))
                if position_amt != 0:
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
            
            logger.info(f"📭 No hay posición en {symbol}")
            return False
            
        except Exception as e:
            logger.error(f"❌ Error cerrando {symbol}: {e}")
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
            logger.error(f"❌ Error posición {symbol}: {e}")
            return None
        