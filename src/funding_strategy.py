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
        # 1. Configuración de Umbrales Realistas
        # El JSON usa 'min_funding_rate' y 'exit_funding_rate'
        self.symbols = config.get('symbols', ['BTC/USDT'])
        
        # Umbral para ENTRAR (0.0001 = 0.01%)
        self.extreme_threshold = config.get('min_funding_rate', 0.0001)
        
        # Umbral para SALIR (0.00005 = 0.005%)
        self.min_threshold = config.get('exit_funding_rate', 0.00005)
        
        self.max_position_size = config.get('max_position_size_usd', 100)
        self.leverage = config.get('leverage', 5)
        self.max_positions = config.get('max_positions', 3)
        
        # Estado Interno
        self.history: Dict[str, List[float]] = {s: [] for s in self.symbols}
        self.max_history = 20
        self.positions: Dict[str, Dict] = {}
        
        logger.info(f"🚀 Estrategia Optimizada: {len(self.symbols)} pares | "
                    f"Entrada: {self.extreme_threshold*100:.4f}% | "
                    f"Salida: {self.min_threshold*100:.4f}%")

    def update(self, symbol: str, funding_data: Dict, ticker_data: Dict) -> Optional[FundingSignal]:
        """Procesa datos y decide si hay señal de trading"""
        if not funding_data or not ticker_data:
            return None
        
        if symbol not in self.symbols:
            return None
        
        # Actualizar historial y calcular estadísticas
        self._update_history(symbol, funding_data['fundingRate'])
        stats = self._calculate_stats(symbol)
        
        # FILTRO DE VOLATILIDAD: 
        # Si el funding varía demasiado (std > 50% del valor actual), esperamos.
        rate = funding_data['fundingRate']
        if stats['std'] > abs(rate) * 0.5 and len(self.history[symbol]) > 5:
            return None

        return self._evaluate_signal(symbol, funding_data, ticker_data, stats)

    def _update_history(self, symbol: str, rate: float):
        if symbol not in self.history:
            self.history[symbol] = []
        self.history[symbol].append(rate)
        if len(self.history[symbol]) > self.max_history:
            self.history[symbol].pop(0)

    def _calculate_stats(self, symbol: str) -> Dict:
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
        # Solo entramos si el funding actual es consistente con el promedio (filtro de ruido)
        is_stable = abs(rate) >= abs(stats['mean']) * 0.8

        # CASO SHORT: Funding Positivo nos paga por vender
        if rate > self.extreme_threshold and is_stable:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='open_short',
                confidence=self._calculate_confidence(rate),
                expected_profit_bps=(rate * 10000),
                reason=f"🔥 SHORT Rentable: {rate:.4%} (Promedio: {stats['mean']:.4%})"
            )

        # CASO LONG: Funding Negativo nos paga por comprar
        if rate < -self.extreme_threshold and is_stable:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='open_long',
                confidence=self._calculate_confidence(rate),
                expected_profit_bps=(abs(rate) * 10000),
                reason=f"❄️ LONG Rentable: {rate:.4%} (Promedio: {stats['mean']:.4%})"
            )
        
        return None

    def _evaluate_exit(self, symbol: str, rate: float, mark: float, stats: Dict) -> Optional[FundingSignal]:
        position = self.positions[symbol]
        side = position['side']
        
        # 1. Salida si la tasa baja del umbral de rentabilidad mínima
        if abs(rate) < self.min_threshold:
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='close',
                confidence=1.0,
                expected_profit_bps=0,
                reason=f"📉 Salida: Funding {rate:.4%} ya no compensa comisiones"
            )
        
        # 2. Salida si el signo cambia (evitar pagar nosotros)
        if (side == 'short' and rate < 0) or (side == 'long' and rate > 0):
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='close',
                confidence=1.0,
                expected_profit_bps=0,
                reason=f"🔄 Salida: Cambio de polaridad en tasa ({rate:.4%})"
            )
        
        return None

    def _calculate_confidence(self, rate: float) -> float:
        # Escala la confianza entre 0.5 y 1.0 dependiendo de qué tan extremo sea el funding
        norm_rate = abs(rate) / (self.extreme_threshold * 2)
        return max(0.5, min(norm_rate, 1.0))

    def calculate_size(self, confidence: float, available_usdt: float) -> float:
        """Calcula el tamaño de la posición en USD usando apalancamiento"""
        # Reservamos el 20% para margen de seguridad
        safe_capital = available_usdt * 0.8
        
        # Tamaño basado en apalancamiento y confianza
        size_with_leverage = safe_capital * self.leverage * confidence
        
        # Capamos al máximo por posición definido en config (multiplicado por leverage)
        limit_size = self.max_position_size * self.leverage
        
        final_size = min(size_with_leverage, limit_size)
        
        # Mínimo de Binance suele ser $10-15 USD notional
        return round(final_size, 2) if final_size >= 15.0 else 0.0

    def register_position(self, symbol: str, side: str, entry_rate: float, size_usd: float):
        self.positions[symbol] = {
            'side': side.lower(),
            'entry_rate': entry_rate,
            'entry_time': datetime.now(),
            'size_usd': size_usd
        }
        logger.info(f"✅ Posición Registrada: {symbol} {side.upper()} | Tasa: {entry_rate:.4%}")

    def clear_position(self, symbol: str):
        if symbol in self.positions:
            entry_time = self.positions[symbol]['entry_time']
            duration = datetime.now() - entry_time
            logger.info(f"🧹 Limpiando datos de {symbol} | Duración: {duration}")
            del self.positions[symbol]

    def get_active_positions(self) -> List[str]:
        return list(self.positions.keys())

    def get_position_count(self) -> int:
        return len(self.positions)

    def get_positions_for_dashboard(self) -> Dict:
        return {s: {**p, 'entry_time': p['entry_time'].isoformat()} 
                for s, p in self.positions.items()}