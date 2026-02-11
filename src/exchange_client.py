import os
import ccxt
from typing import Dict, Optional
from loguru import logger

class BinanceClient:
    """Cliente Binance Futures - Solo endpoints fapi, optimizado para precisión"""
    
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
            logger.info("📝 Futures DEMO habilitado")
        else:
            logger.warning("💰 Futures REAL habilitado")
        
        return exchange
    
    def load_markets(self) -> bool:
        """Carga mercados y guarda reglas de precisión"""
        try:
            response = self.exchange.fetch2('exchangeInfo', 'fapiPublic')
            markets = {}
            for symbol_data in response.get('symbols', []):
                if symbol_data.get('status') == 'TRADING':
                    symbol = symbol_data['symbol'] # Formato sin barra (BTCUSDT)
                    # Mapeamos con barra para compatibilidad con el resto del bot
                    symbol_formatted = f"{symbol_data['baseAsset']}/{symbol_data['quoteAsset']}"
                    markets[symbol_formatted] = {
                        'symbol': symbol,
                        'precision': {
                            'amount': int(symbol_data.get('quantityPrecision', 3)),
                            'price': int(symbol_data.get('pricePrecision', 2)),
                        }
                    }
            
            self.markets = markets
            logger.info(f"✅ {len(markets)} mercados cargados con reglas de precisión")
            return True
        except Exception as e:
            logger.error(f"❌ Error cargando mercados: {e}")
            return False
    
    def fetch_balance(self) -> Optional[Dict]:
        """Obtiene balance real de la cuenta de Futures"""
        try:
            response = self.exchange.fetch2('account', 'fapiPrivateV2')
            assets = response.get('assets', [])
            balance = {
                'USDT': {'free': 0.0, 'used': 0.0, 'total': 0.0},
                'USDC': {'free': 0.0, 'used': 0.0, 'total': 0.0},
                'BTC': {'free': 0.0, 'used': 0.0, 'total': 0.0},
            }
            
            for asset in assets:
                name = asset.get('asset', '')
                if name in balance:
                    available = float(asset.get('availableBalance', 0))
                    wallet = float(asset.get('walletBalance', 0))
                    balance[name] = {
                        'free': available,
                        'used': wallet - available,
                        'total': wallet
                    }
            
            # Actualizar cache para visualización
            self._balance_cache = {k: v['free'] for k, v in balance.items()}
            return balance
        except Exception as e:
            logger.error(f"❌ Error balance: {e}")
            return None

    def create_order(self, symbol: str, side: str, amount: float, 
                     price: float = None, order_type: str = 'limit') -> Optional[Dict]:
        """Crea una orden respetando estrictamente las precisiones de Binance"""
        try:
            symbol_fapi = symbol.replace('/', '')
            
            # 1. Validar y formatear Cantidad
            qty = self._round_amount(symbol, amount)
            
            params = {
                'symbol': symbol_fapi,
                'side': side.upper(),
                'type': order_type.upper(),
                'quantity': qty,
            }
            
            # 2. Si es Limit, validar y formatear Precio
            if order_type.lower() == 'limit' and price:
                params['price'] = self._round_price(symbol, price)
                params['timeInForce'] = 'GTC'
            
            response = self.exchange.fetch2('order', 'fapiPrivate', 'POST', params)
            
            order_id = response.get('orderId')
            logger.info(f"✅ Orden {side} enviada en {symbol}: ID {order_id}")
            return {'id': order_id, 'status': response.get('status')}
            
        except Exception as e:
            logger.error(f"❌ Error al enviar orden en {symbol}: {e}")
            return None

    def _round_amount(self, symbol: str, amount: float) -> float:
        """Redondea cantidad según precisión de activos (Error -1111)"""
        try:
            if not self.markets or symbol not in self.markets:
                return round(amount, 2)
            precision = self.markets[symbol]['precision']['amount']
            # El truco del format elimina decimales fantasma de Python
            return float(f"{{:.{precision}f}}".format(amount))
        except:
            return round(amount, 2)

    def _round_price(self, symbol: str, price: float) -> float:
        """Redondea precio según precisión del mercado"""
        try:
            if not self.markets or symbol not in self.markets:
                return round(price, 2)
            precision = self.markets[symbol]['precision']['price']
            return float(f"{{:.{precision}f}}".format(price))
        except:
            return round(price, 2)

    def close_position(self, symbol: str) -> bool:
        """Cierra cualquier posición abierta en el símbolo mediante orden MARKET"""
        try:
            symbol_fapi = symbol.replace('/', '')
            response = self.exchange.fetch2('positionRisk', 'fapiPrivate', 'GET', {'symbol': symbol_fapi})
            
            positions = response if isinstance(response, list) else [response]
            for pos in positions:
                amt = float(pos.get('positionAmt', 0))
                if amt != 0:
                    side = 'SELL' if amt > 0 else 'BUY'
                    # El cierre siempre es MARKET para asegurar ejecución
                    self.exchange.fetch2('order', 'fapiPrivate', 'POST', {
                        'symbol': symbol_fapi,
                        'side': side,
                        'type': 'MARKET',
                        'quantity': abs(amt),
                        'reduceOnly': 'true'
                    })
                    logger.info(f"✅ Posición cerrada en {symbol}")
                    return True
            return False
        except Exception as e:
            logger.error(f"❌ Error cerrando posición en {symbol}: {e}")
            return False

    def fetch_funding_rate(self, symbol: str) -> Optional[Dict]:
        """Obtiene tasa de financiación actual"""
        try:
            symbol_fapi = symbol.replace('/', '')
            res = self.exchange.fetch2('premiumIndex', 'fapiPublic', 'GET', {'symbol': symbol_fapi})
            return {
                'symbol': symbol,
                'fundingRate': float(res.get('lastFundingRate', 0)),
                'markPrice': float(res.get('markPrice', 0)),
                'nextFundingTime': res.get('nextFundingTime'),
            }
        except Exception as e:
            logger.error(f"❌ Error funding {symbol}: {e}")
            return None

    def fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """Obtiene precios actuales (bid/ask)"""
        try:
            symbol_fapi = symbol.replace('/', '')
            res = self.exchange.fetch2('ticker/24hr', 'fapiPublic', 'GET', {'symbol': symbol_fapi})
            return {
                'last': float(res.get('lastPrice', 0)),
                'bid': float(res.get('bidPrice', 0)),
                'ask': float(res.get('askPrice', 0)),
            }
        except Exception as e:
            logger.error(f"❌ Error ticker {symbol}: {e}")
            return None