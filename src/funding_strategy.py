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
    index_price: float
    action: str
    confidence: float
    expected_profit_bps: float
    reason: str

class FundingArbitrageStrategy:
    def __init__(self, config: Dict):
        self.symbol = config.get('symbol', 'BTC/USDT')
        self.min_threshold = config.get('min_funding_threshold', 0.0005)
        self.extreme_threshold = config.get('extreme_funding_threshold', 0.001)
        self.max_position_size = config.get('max_position_size_usd', 100)
        self.leverage = config.get('leverage', 2)
        self.history: List[float] = []
        self.max_history = 20
        self.position = None
        
    def update(self, funding_data: Dict, ticker_data: Dict) -> Optional[FundingSignal]:
        if not funding_data or not ticker_data:
            return None
        
        self._update_history(funding_data['fundingRate'])
        stats = self._calculate_stats()
        signal = self._evaluate_signal(funding_data, ticker_data, stats)
        
        if signal:
            self._log_signal(signal, stats)
        return signal
    
    def _update_history(self, rate: float):
        self.history.append(rate)
        if len(self.history) > self.max_history:
            self.history.pop(0)
    
    def _calculate_stats(self) -> Dict:
        if not self.history:
            return {'mean': 0, 'std': 0, 'min': 0, 'max': 0}
        return {
            'mean': statistics.mean(self.history),
            'std': statistics.stdev(self.history) if len(self.history) > 1 else 0,
            'min': min(self.history),
            'max': max(self.history),
            'last': self.history[-1]
        }
    
    def _evaluate_signal(self, funding: Dict, ticker: Dict, stats: Dict) -> Optional[FundingSignal]:
        rate = funding['fundingRate']
        mark = funding['markPrice']
        index = funding.get('indexPrice', mark)
        
        if not self.position:
            return self._evaluate_entry(rate, mark, index, stats)
        else:
            return self._evaluate_exit(rate, mark, index, stats)
    
    def _evaluate_entry(self, rate: float, mark: float, index: float, stats: Dict) -> Optional[FundingSignal]:
        if rate > self.extreme_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=self.symbol,
                funding_rate=rate,
                mark_price=mark,
                index_price=index,
                action='open_short',
                confidence=min(rate / self.extreme_threshold, 1.0),
                expected_profit_bps=(rate * 3) * 10000,
                reason=f"Funding alto: {rate:.4%}"
            )
        
        if rate < -self.extreme_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=self.symbol,
                funding_rate=rate,
                mark_price=mark,
                index_price=index,
                action='open_long',
                confidence=min(abs(rate) / self.extreme_threshold, 1.0),
                expected_profit_bps=(abs(rate) * 3) * 10000,
                reason=f"Funding bajo: {rate:.4%}"
            )
        return None
    
    def _evaluate_exit(self, rate: float, mark: float, index: float, stats: Dict) -> Optional[FundingSignal]:
        side = self.position['side']
        
        if abs(rate) < self.min_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=self.symbol,
                funding_rate=rate,
                mark_price=mark,
                index_price=index,
                action='close',
                confidence=0.9,
                expected_profit_bps=0,
                reason=f"Funding normalizado: {rate:.4%}"
            )
        
        if side == 'short' and rate < -self.min_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=self.symbol,
                funding_rate=rate,
                mark_price=mark,
                index_price=index,
                action='close_and_reverse',
                confidence=0.7,
                expected_profit_bps=abs(rate) * 2 * 10000,
                reason=f"Inversión: {self.position['entry_rate']:.4%} → {rate:.4%}"
            )
        
        if side == 'long' and rate > self.min_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=self.symbol,
                funding_rate=rate,
                mark_price=mark,
                index_price=index,
                action='close_and_reverse',
                confidence=0.7,
                expected_profit_bps=rate * 2 * 10000,
                reason=f"Inversión: {self.position['entry_rate']:.4%} → {rate:.4%}"
            )
        return None
    
    def _log_signal(self, signal: FundingSignal, stats: Dict):
        logger.info(
            f"SEÑAL {signal.action.upper()} | "
            f"Funding: {signal.funding_rate:.4%} | "
            f"Conf: {signal.confidence:.0%} | "
            f"Profit: {signal.expected_profit_bps:.1f}bps"
        )
    
    def register_position(self, side: str, entry_rate: float):
        self.position = {
            'side': side,
            'entry_rate': entry_rate,
            'entry_time': datetime.now()
        }
        logger.info(f"Posición: {side} @ {entry_rate:.4%}")
    
    def clear_position(self):
        if self.position:
            duration = datetime.now() - self.position['entry_time']
            logger.info(f"Posición cerrada. Duración: {duration}")
            self.position = None
    
    def calculate_size(self, confidence: float, available_usdt: float) -> float:
        max_size = min(self.max_position_size, available_usdt * 0.5)
        size = max_size * confidence
        return round(size, 2) if size >= 10 else 0

