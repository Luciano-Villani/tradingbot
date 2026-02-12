from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime
import statistics
from loguru import logger

@dataclass
class FundingSignal:
    timestamp: datetime
    symbol: str
    funding_rate: float
    mark_price: float
    action: str
    confidence: float
    expected_profit_bps: float
    reason: str

class FundingArbitrageStrategy:
    def __init__(self, config: Dict):
        # --- CORRECCIÓN DE CARGA DE SÍMBOLOS ---
        # Forzamos a que lea del JSON. Si no existe, no arranca.
        self.symbols = config.get('symbols')
        if not self.symbols:
            logger.error("❌ No se encontraron símbolos en settings.json")
            self.symbols = [] # Evita que explote, pero logger avisará
        
        # Umbrales desde el JSON
        self.extreme_threshold = config.get('min_funding_rate', 0.0001)
        self.min_threshold = config.get('exit_funding_rate', 0.00005)
        self.max_position_size = config.get('max_position_size_usd', 100)
        self.leverage = config.get('leverage', 5)
        self.max_positions = config.get('max_positions', 3)
        
        # --- SINCRONIZACIÓN DE HISTORIAL ---
        # Solo creamos historial para los símbolos EXACTOS de la lista
        self.history: Dict[str, List[float]] = {s: [] for s in self.symbols}
        self.max_history = 20
        self.positions: Dict[str, Dict] = {}
        
        logger.info(f"✅ Estrategia Sincronizada: {len(self.symbols)} pares reales.")

    def update(self, symbol: str, funding_data: Dict, ticker_data: Dict) -> Optional[FundingSignal]:
        """Procesa datos y decide si hay señal de trading"""
        if not funding_data or not ticker_data:
            return None
        
        # FILTRO DE SEGURIDAD: Ignorar si el símbolo no está en nuestra lista de 8
        if symbol not in self.symbols:
            return None
        
        # Asegurar que el símbolo tenga espacio en el historial (prevención de errores)
        if symbol not in self.history:
            self.history[symbol] = []
            
        self._update_history(symbol, funding_data['fundingRate'])
        stats = self._calculate_stats(symbol)
        
        rate = funding_data['fundingRate']
        
        # Filtro de Volatilidad: Evita entrar si el funding es inestable
        if len(self.history[symbol]) > 5:
            if stats['std'] > abs(rate) * 0.5:
                # logger.debug(f"⚠️ {symbol} inestable, esperando estabilidad.")
                return None

        return self._evaluate_signal(symbol, funding_data, ticker_data, stats)

    def _update_history(self, symbol: str, rate: float):
        self.history[symbol].append(rate)
        if len(self.history[symbol]) > self.max_history:
            self.history[symbol].pop(0)

    def _calculate_stats(self, symbol: str) -> Dict:
        hist = self.history.get(symbol, [])
        if not hist or len(hist) < 2:
            return {'mean': 0, 'std': 0, 'min': 0, 'max': 0}
        
        return {
            'mean': statistics.mean(hist),
            'std': statistics.stdev(hist),
            'min': min(hist),
            'max': max(hist),
        }

    def _evaluate_signal(self, symbol: str, funding: Dict, ticker: Dict, stats: Dict) -> Optional[FundingSignal]:
        rate = funding['fundingRate']
        mark = funding['markPrice']
        has_position = symbol in self.positions
        
        if not has_position:
            if len(self.positions) >= self.max_positions:
                return None
            return self._evaluate_entry(symbol, rate, mark, stats)
        else:
            return self._evaluate_exit(symbol, rate, mark, stats)

    def _evaluate_entry(self, symbol: str, rate: float, mark: float, stats: Dict) -> Optional[FundingSignal]:
        # Filtro de consistencia: El valor actual no debe ser un "outlier" (pico loco)
        is_stable = abs(rate) >= abs(stats['mean']) * 0.7

        # SHORT: Funding positivo (nos pagan)
        if rate > self.extreme_threshold and is_stable:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='open_short',
                confidence=self._calculate_confidence(rate),
                expected_profit_bps=(rate * 10000),
                reason=f"🔥 SHORT: {rate:.4%} estable"
            )

        # LONG: Funding negativo (nos pagan)
        if rate < -self.extreme_threshold and is_stable:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='open_long',
                confidence=self._calculate_confidence(rate),
                expected_profit_bps=(abs(rate) * 10000),
                reason=f"❄️ LONG: {rate:.4%} estable"
            )
        
        return None

    def _evaluate_exit(self, symbol: str, rate: float, mark: float, stats: Dict) -> Optional[FundingSignal]:
        position = self.positions[symbol]
        side = position['side']
        
        # Salida por baja rentabilidad
        if abs(rate) < self.min_threshold:
            return FundingSignal(
                timestamp=datetime.now(), symbol=symbol, funding_rate=rate, mark_price=mark,
                action='close', confidence=1.0, expected_profit_bps=0,
                reason=f"📉 Normalizado: {rate:.4%}"
            )
        
        # Salida por cambio de signo
        if (side == 'short' and rate < 0) or (side == 'long' and rate > 0):
            return FundingSignal(
                timestamp=datetime.now(), symbol=symbol, funding_rate=rate, mark_price=mark,
                action='close', confidence=1.0, expected_profit_bps=0,
                reason=f"🔄 Inversión de tasa: {rate:.4%}"
            )
        
        return None

    def _calculate_confidence(self, rate: float) -> float:
        norm_rate = abs(rate) / (self.extreme_threshold * 1.5)
        return max(0.6, min(norm_rate, 1.0))

    def calculate_size(self, confidence: float, available_usdt: float) -> float:
        safe_capital = available_usdt * 0.8
        size_with_leverage = safe_capital * self.leverage * confidence
        limit_size = self.max_position_size * self.leverage
        final_size = min(size_with_leverage, limit_size)
        return round(final_size, 2) if final_size >= 15.0 else 0.0

    def register_position(self, symbol: str, side: str, entry_rate: float, size_usd: float):
        self.positions[symbol] = {
            'side': side.lower(),
            'entry_rate': entry_rate,
            'entry_time': datetime.now(),
            'size_usd': size_usd
        }

    def clear_position(self, symbol: str):
        if symbol in self.positions:
            del self.positions[symbol]

    def get_active_positions(self) -> List[str]:
        return list(self.positions.keys())

    def get_position_count(self) -> int:
        return len(self.positions)

    def get_positions_for_dashboard(self) -> Dict:
        return {s: {**p, 'entry_time': p['entry_time'].isoformat()} 
                for s, p in self.positions.items()}
    