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
        self.symbols = config.get('symbols', ['BTC/USDT'])
        self.min_threshold = config.get('min_funding_threshold', 0.0005)
        self.extreme_threshold = config.get('extreme_threshold', 0.001)
        self.max_position_size = config.get('max_position_size_usd', 100)
        self.leverage = config.get('leverage', 2)
        self.max_positions = config.get('max_positions', 3)
        
        self.history: Dict[str, List[float]] = {s: [] for s in self.symbols}
        self.max_history = 20
        self.positions: Dict[str, Dict] = {}
        
        logger.info(f"Estrategia: {len(self.symbols)} pares | Max pos: {self.max_positions}")
    
    def update(self, symbol: str, funding_data: Dict, ticker_data: Dict) -> Optional[FundingSignal]:
        """Procesa datos de un par específico"""
        
        if not funding_data or not ticker_data:
            return None
        
        if symbol not in self.symbols:
            return None
        
        self._update_history(symbol, funding_data['fundingRate'])
        stats = self._calculate_stats(symbol)
        signal = self._evaluate_signal(symbol, funding_data, ticker_data, stats)
        
        return signal
    
    def _update_history(self, symbol: str, rate: float):
        """Mantiene historial por símbolo"""
        self.history[symbol].append(rate)
        if len(self.history[symbol]) > self.max_history:
            self.history[symbol].pop(0)
    
    def _calculate_stats(self, symbol: str) -> Dict:
        """Estadísticas del historial de un símbolo"""
        hist = self.history.get(symbol, [])
        if not hist:
            return {'mean': 0, 'std': 0, 'min': 0, 'max': 0}
        
        return {
            'mean': statistics.mean(hist),
            'std': statistics.stdev(hist) if len(hist) > 1 else 0,
            'min': min(hist),
            'max': max(hist),
        }
    
    def _evaluate_signal(self, symbol: str, funding: Dict, ticker: Dict, stats: Dict) -> Optional[FundingSignal]:
        """Evalúa si operar en este par"""
        
        rate = funding['fundingRate']
        mark = funding['markPrice']
        has_position = symbol in self.positions
        total_positions = len(self.positions)
        
        if not has_position:
            if total_positions >= self.max_positions:
                return None
            return self._evaluate_entry(symbol, rate, mark, stats)
        else:
            return self._evaluate_exit(symbol, rate, mark, stats)
    
    def _evaluate_entry(self, symbol: str, rate: float, mark: float, stats: Dict) -> Optional[FundingSignal]:
        """Evalúa entrada en un par"""
        
        if rate > self.extreme_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='open_short',
                confidence=min(rate / self.extreme_threshold, 1.0),
                expected_profit_bps=(rate * 3) * 10000,
                reason=f"{symbol} funding ALTO: {rate:.4%} → SHORT"
            )
        
        if rate < -self.extreme_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='open_long',
                confidence=min(abs(rate) / self.extreme_threshold, 1.0),
                expected_profit_bps=(abs(rate) * 3) * 10000,
                reason=f"{symbol} funding BAJO: {rate:.4%} → LONG"
            )
        
        return None
    
    def _evaluate_exit(self, symbol: str, rate: float, mark: float, stats: Dict) -> Optional[FundingSignal]:
        """Evalúa salida de posición existente"""
        
        position = self.positions[symbol]
        side = position['side']
        entry_rate = position['entry_rate']
        
        if abs(rate) < self.min_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='close',
                confidence=0.9,
                expected_profit_bps=0,
                reason=f"{symbol} funding NORMALIZADO: {rate:.4%} → CERRAR"
            )
        
        if side == 'short' and rate < -self.min_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='close_and_reverse',
                confidence=0.7,
                expected_profit_bps=abs(rate) * 2 * 10000,
                reason=f"{symbol} INVERSIÓN: {entry_rate:.4%} → {rate:.4%}"
            )
        
        if side == 'long' and rate > self.min_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='close_and_reverse',
                confidence=0.7,
                expected_profit_bps=rate * 2 * 10000,
                reason=f"{symbol} INVERSIÓN: {entry_rate:.4%} → {rate:.4%}"
            )
        
        return None
    
    def register_position(self, symbol: str, side: str, entry_rate: float, size_usd: float):
        """Registra apertura de posición"""
        self.positions[symbol] = {
            'side': side,
            'entry_rate': entry_rate,
            'entry_time': datetime.now(),
            'size_usd': size_usd
        }
        logger.info(f"📈 {symbol}: {side.upper()} @ {entry_rate:.4%} | ${size_usd:.2f}")
    
    def clear_position(self, symbol: str):
        """Limpia posición al cerrar"""
        if symbol in self.positions:
            duration = datetime.now() - self.positions[symbol]['entry_time']
            logger.info(f"📭 {symbol} cerrado | Duración: {duration}")
            del self.positions[symbol]
    
    def calculate_size(self, confidence: float, available_usdt: float) -> float:
        """Calcula tamaño de posición"""
        max_size = min(self.max_position_size, available_usdt * 0.5)
        size = max_size * confidence
        return round(size, 2) if size >= 10 else 0
    
    def get_active_positions(self) -> List[str]:
        """Retorna lista de pares con posición abierta"""
        return list(self.positions.keys())
    
    def get_position_count(self) -> int:
        """Cantidad de posiciones abiertas"""
        return len(self.positions)
    
    def get_positions_for_dashboard(self) -> Dict:
        """Retorna posiciones formateadas para dashboard"""
        result = {}
        for symbol, pos in self.positions.items():
            result[symbol] = {
                'side': pos['side'],
                'size_usd': pos['size_usd'],
                'entry_rate': pos['entry_rate'],
                'pnl': 0  # Se actualizaría con datos reales
            }
        return result
    