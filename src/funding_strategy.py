from dataclasses import dataclass
from typing import Optional, Dict, List
from datetime import datetime, timedelta, timezone
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
    next_funding_time: Optional[datetime] = None  # NUEVO: Para sincronización
    cycles_captured: int = 0  # NUEVO: Al cerrar, cuántos ciclos se capturaron

class FundingArbitrageStrategy:
    def __init__(self, config: Dict):
        # --- CORRECCIÓN DE CARGA DE SÍMBOLOS ---
        self.symbols = config.get('symbols')
        if not self.symbols:
            logger.error("❌ No se encontraron símbolos en settings.json")
            self.symbols = []
        
        # Umbrales desde el JSON
        self.extreme_threshold = config.get('min_funding_rate', 0.0001)
        self.min_threshold = config.get('exit_funding_rate', 0.00005)
        self.max_position_size = config.get('max_position_size_usd', 100)
        self.leverage = config.get('leverage', 5)
        self.max_positions = config.get('max_positions', 3)
        
        # --- NUEVO: CONFIGURACIÓN DE FUNDING ---
        self.funding_hours = [0, 8, 16]  # Binance: 00:00, 08:00, 16:00 UTC
        self.funding_interval_hours = 8
        
        # --- SINCRONIZACIÓN DE HISTORIAL ---
        self.history: Dict[str, List[float]] = {s: [] for s in self.symbols}
        self.max_history = 20
        self.positions: Dict[str, Dict] = {}
        
        # --- NUEVO: BREAK-EVEN CALCULATOR ---
        self.estimated_slippage_bps = 5  # 0.05% entrada + salida
        self.taker_fee_bps = 4  # 0.04%
        self.maker_fee_bps = 2  # 0.02%
        self.break_even_rate = self._calculate_break_even_rate()
        
        logger.info(f"✅ Estrategia: {len(self.symbols)} pares | Break-even: {self.break_even_rate:.4%}")

    def _calculate_break_even_rate(self) -> float:
        """Calcula el funding rate mínimo para ser rentable"""
        # Costos: slippage (ida y vuelta) + comisiones (entrada + salida)
        total_cost_bps = self.estimated_slippage_bps + (self.taker_fee_bps * 2)
        # Convertir a rate por ciclo de 8 horas
        # Asumimos 1 ciclo mínimo, si queremos más ciclos, dividimos
        return total_cost_bps / 10000

    def _next_funding_time(self, now: datetime = None) -> datetime:
        """Calcula el próximo funding en UTC"""
        if now is None:
            now = datetime.now(timezone.utc)
        
        current_hour = now.hour
        
        for funding_hour in self.funding_hours:
            if current_hour < funding_hour:
                return now.replace(hour=funding_hour, minute=0, second=0, microsecond=0)
        
        # Si pasamos el último de hoy, es mañana a las 00:00
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)

    def _count_funding_cycles(self, entry_time: datetime, exit_time: datetime = None) -> int:
        """Cuenta cuántos pagos de funding ocurrieron entre entry y exit"""
        if exit_time is None:
            exit_time = datetime.now(timezone.utc)
        
        cycles = 0
        current = entry_time.replace(minute=0, second=0, microsecond=0)
        
        # Avanzar hora por hora hasta exit_time
        while current < exit_time:
            if current.hour in self.funding_hours:
                # Verificar que estuvimos en posición durante el snapshot (00:00 UTC)
                snapshot_time = current.replace(minute=0, second=0)
                if entry_time <= snapshot_time:
                    cycles += 1
            current += timedelta(hours=1)
        
        return cycles

    def _time_to_next_funding(self, now: datetime = None) -> float:
        """Minutos hasta el próximo funding"""
        if now is None:
            now = datetime.now(timezone.utc)
        next_funding = self._next_funding_time(now)
        return (next_funding - now).total_seconds() / 60

    def update(self, symbol: str, funding_data: Dict, ticker_data: Dict) -> Optional[FundingSignal]:
        """Procesa datos y decide si hay señal de trading"""
        if not funding_data or not ticker_data:
            return None
        
        if symbol not in self.symbols:
            return None
        
        if symbol not in self.history:
            self.history[symbol] = []
            
        self._update_history(symbol, funding_data['fundingRate'])
        stats = self._calculate_stats(symbol)
        
        rate = funding_data['fundingRate']
        
        # Filtro de Volatilidad
        if len(self.history[symbol]) > 5:
            if stats['std'] > abs(rate) * 0.5:
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
        # NUEVO: Filtro de rentabilidad mínima
        if abs(rate) < self.break_even_rate:
            return None
            
        # Filtro de consistencia
        is_stable = abs(rate) >= abs(stats['mean']) * 0.7

        next_funding = self._next_funding_time()
        mins_to_funding = self._time_to_next_funding()

        # SHORT: Funding positivo (nos pagan)
        if rate > self.extreme_threshold and is_stable:
            logger.info(f"⏰ {symbol} | Próximo funding: {next_funding.strftime('%H:%M UTC')} ({mins_to_funding:.0f} min)")
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='open_short',
                confidence=self._calculate_confidence(rate),
                expected_profit_bps=(rate * 10000),
                reason=f"🔥 SHORT: {rate:.4%} estable | Break-even: {self.break_even_rate:.4%}",
                next_funding_time=next_funding
            )

        # LONG: Funding negativo (nos pagan)
        if rate < -self.extreme_threshold and is_stable:
            logger.info(f"⏰ {symbol} | Próximo funding: {next_funding.strftime('%H:%M UTC')} ({mins_to_funding:.0f} min)")
            return FundingSignal(
                timestamp=datetime.now(),
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='open_long',
                confidence=self._calculate_confidence(rate),
                expected_profit_bps=(abs(rate) * 10000),
                reason=f"❄️ LONG: {rate:.4%} estable | Break-even: {self.break_even_rate:.4%}",
                next_funding_time=next_funding
            )
        
        return None

    def _evaluate_exit(self, symbol: str, rate: float, mark: float, stats: Dict) -> Optional[FundingSignal]:
        position = self.positions[symbol]
        side = position['side']
        entry_time = position['entry_time']
        now = datetime.now(timezone.utc)
        
        # NUEVO: Calcular métricas de hold
        cycles = self._count_funding_cycles(entry_time, now)
        hold_hours = (now - entry_time).total_seconds() / 3600
        next_funding = self._next_funding_time(now)
        
        logger.info(f"📊 {symbol} | Hold: {hold_hours:.1f}h | Ciclos: {cycles} | Próximo: {next_funding.strftime('%H:%M UTC')}")

        # NUEVO: Salida inteligente basada en ciclos capturados
        # Solo salir si ya capturamos al menos 1 ciclo Y el funding se normalizó
        if cycles >= 1 and abs(rate) < self.min_threshold:
            return FundingSignal(
                timestamp=now,
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='close',
                confidence=0.9,
                expected_profit_bps=0,
                reason=f"📉 Cerrado: {cycles} ciclo(s) capturado(s), funding {rate:.4%}",
                next_funding_time=next_funding,
                cycles_captured=cycles
            )
        
        # Salida por cambio de signo (solo si ya capturamos algo)
        if cycles >= 1 and ((side == 'short' and rate < 0) or (side == 'long' and rate > 0)):
            return FundingSignal(
                timestamp=now,
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='close',
                confidence=1.0,
                expected_profit_bps=0,
                reason=f"🔄 Inversión tras {cycles} ciclo(s): {rate:.4%}",
                next_funding_time=next_funding,
                cycles_captured=cycles
            )
        
        # Si no hemos capturado ningún ciclo, mantener a menos que sea crítico
        if cycles == 0 and abs(rate) < self.break_even_rate * 0.5:
            return FundingSignal(
                timestamp=now,
                symbol=symbol,
                funding_rate=rate,
                mark_price=mark,
                action='close',
                confidence=0.5,
                expected_profit_bps=-self.break_even_rate * 10000,
                reason=f"⛔ Stop: Sin ciclos capturados, funding colapsó a {rate:.4%}",
                next_funding_time=next_funding,
                cycles_captured=0
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
            'entry_time': datetime.now(timezone.utc),  # NUEVO: Forzar UTC
            'size_usd': size_usd
        }

    def clear_position(self, symbol: str):
        if symbol in self.positions:
            entry_time = self.positions[symbol]['entry_time']
            exit_time = datetime.now(timezone.utc)
            duration = exit_time - entry_time
            cycles = self._count_funding_cycles(entry_time, exit_time)
            logger.info(f"📭 {symbol} cerrado | Duración: {duration} | Ciclos capturados: {cycles}")
            del self.positions[symbol]

    def get_active_positions(self) -> List[str]:
        return list(self.positions.keys())

    def get_position_count(self) -> int:
        return len(self.positions)

    def get_positions_for_dashboard(self) -> Dict:
        result = {}
        for symbol, pos in self.positions.items():
            now = datetime.now(timezone.utc)
            cycles = self._count_funding_cycles(pos['entry_time'], now)
            hold_hours = (now - pos['entry_time']).total_seconds() / 3600
            
            result[symbol] = {
                'side': pos['side'],
                'size_usd': pos['size_usd'],
                'entry_rate': pos['entry_rate'],
                'hold_hours': round(hold_hours, 1),
                'cycles_captured': cycles,
                'next_funding': self._next_funding_time(now).strftime('%H:%M UTC')
            }
        return result
        
    def get_position_metrics(self, symbol: str) -> Dict:
        """NUEVO: Métricas detalladas para el logger"""
        if symbol not in self.positions:
            return {}
        
        pos = self.positions[symbol]
        now = datetime.now(timezone.utc)
        cycles = self._count_funding_cycles(pos['entry_time'], now)
        hold_hours = (now - pos['entry_time']).total_seconds() / 3600
        
        return {
            'entry_time': pos['entry_time'],
            'hold_hours': hold_hours,
            'cycles_captured': cycles,
            'next_funding_time': self._next_funding_time(now)
        }
    