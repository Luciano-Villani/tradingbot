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
        """Carga mercados usando solo fapi y extrae filtros de tick y step"""
        try:
            response = self.exchange.fetch2('exchangeInfo', 'fapiPublic')
            
            markets = {}
            for symbol_data in response.get('symbols', []):
                if symbol_data.get('status') == 'TRADING':
                    symbol = symbol_data['symbol']
                    
                    # Extraemos los filtros necesarios para el redondeo matemático
                    filters = {f['filterType']: f for f in symbol_data.get('filters', [])}
                    
                    # El tickSize es el incremento mínimo de precio (ej. 0.10, 0.01)
                    price_filter = filters.get('PRICE_FILTER', {})
                    tick_size = price_filter.get('tickSize', '0.01')
                    
                    # El stepSize es el incremento mínimo de cantidad (ej. 0.001, 1.0)
                    lot_filter = filters.get('LOT_SIZE', {})
                    step_size = lot_filter.get('stepSize', '0.01')
                    
                    markets[symbol] = {
                        'symbol': symbol,
                        'base': symbol_data['baseAsset'],
                        'quote': symbol_data['quoteAsset'],
                        'precision': {
                            'amount': int(symbol_data.get('quantityPrecision', 3)),
                            'price': int(symbol_data.get('pricePrecision', 2)),
                        },
                        'tickSize': float(tick_size),
                        'stepSize': float(step_size)
                    }
            
            self.markets = markets
            logger.info(f"✅ {len(markets)} mercados cargados con filtros de precisión")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error cargando mercados: {e}")
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
        """Crear orden con redondeo estricto de cantidad y precio"""
        try:
            symbol_fapi = symbol.replace('/', '')
            
            # Redondeo de cantidad
            qty = self._round_amount(symbol, amount)
            
            if qty <= 0:
                logger.error(f"❌ Cantidad redondeada es 0 o negativa para {symbol}. Amount original: {amount}")
                return None

            params = {
                'symbol': symbol_fapi,
                'side': side.upper(),
                'type': order_type.upper(),
                'quantity': qty,
            }
            
            if order_type.lower() == 'limit' and price:
                # IMPORTANTE: También redondeamos el precio
                params['price'] = self._round_price(symbol, price)
                params['timeInForce'] = 'GTC'
            
            # Log de depuración para ver qué enviamos exactamente
            logger.debug(f"Enviando a Binance: {params}")
            
            response = self.exchange.fetch2('order', 'fapiPrivate', 'POST', params)
            
            order_id = response.get('orderId')
            logger.info(f"🚀 ORDEN EJECUTADA: {symbol} {side} | ID: {order_id}")
            return {
                'id': order_id,
                'status': response.get('status'),
            }
        except Exception as e:
            logger.error(f"❌ Error orden en {symbol}: {e}")
            return None

    def _round_price(self, symbol: str, price: float) -> float:
        """Redondea el precio al múltiplo de tickSize más cercano"""
        try:
            symbol_key = symbol.replace('/', '')
            if not self.markets or symbol_key not in self.markets:
                return round(float(price), 2)
            
            tick_size = self.markets[symbol_key].get('tickSize', 0.01)
            precision = self.markets[symbol_key]['precision']['price']
            
            # Matemática de tick: (Precio // tickSize) * tickSize
            rounded = (float(price) // tick_size) * tick_size
            return float(f"{{:.{precision}f}}".format(rounded))
        except Exception as e:
            logger.error(f"Error redondeo precio {symbol}: {e}")
            return float(price)

    def _round_amount(self, symbol: str, amount: float) -> float:
        """Redondea la cantidad al múltiplo de stepSize más cercano"""
        try:
            symbol_key = symbol.replace('/', '')
            if not self.markets or symbol_key not in self.markets:
                return round(float(amount), 3)
            
            step_size = self.markets[symbol_key].get('stepSize', 0.01)
            precision = self.markets[symbol_key]['precision']['amount']
            
            rounded = (float(amount) // step_size) * step_size
            return float(f"{{:.{precision}f}}".format(rounded))
        except Exception as e:
            logger.error(f"Error redondeo cantidad {symbol}: {e}")
            return float(amount)
    
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
        