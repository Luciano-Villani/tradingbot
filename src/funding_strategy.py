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
        # ... (carga de símbolos igual) ...
        self.symbols = config.get('symbols', [])

        # --- CORRECCIÓN DE NOMBRES ---
        # Buscamos los nombres exactos que pusiste en settings.json
        self.extreme_threshold = config.get('min_funding_rate_threshold', 0.015) / 100 # Convertir 0.015 a 0.00015
        self.min_threshold = config.get('buffer_over_fees', 0.005) / 100
        
        self.max_position_size = config.get('max_position_size_usd', 100)
        self.leverage = config.get('leverage', 5)
        self.max_positions = config.get('max_positions', 3)
        
        self.funding_hours = [0, 8, 16]
        self.history: Dict[str, List[float]] = {s: [] for s in self.symbols}
        self.max_history = 20
        self.positions: Dict[str, Dict] = {}
        
        # --- AJUSTE DE COSTOS REALISTAS ---
        self.estimated_slippage_bps = 1  # Bajamos a 2 bps (0.02%)
        self.taker_fee_bps = 2           # 0.04% (Binance Standard)
        self.break_even_rate = self._calculate_break_even_rate()
        
        logger.info(f"✅ Estrategia: {len(self.symbols)} pares | Break-even: {self.break_even_rate:.4%}")

    def _calculate_break_even_rate(self) -> float:
        """Calcula el funding rate mínimo considerando una estancia de al menos 2 ciclos"""
        # Costo total ida y vuelta: (2 de slippage + 8 de comisiones) = 10 bps
        total_cost_bps = self.estimated_slippage_bps + (self.taker_fee_bps * 2)
        
        # Dividimos por 2 ciclos para ser más agresivos. 
        # Si la tasa es > 0.05% (5 bps), en dos pagos cubrimos los gastos.
        return (total_cost_bps / 2) / 10000
    
    def _next_funding_time(self, now: datetime = None) -> datetime:
        """Calcula el próximo ciclo de funding (00:00, 08:00, 16:00 UTC)"""
        # 1. Forzar UTC explícitamente
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            # Si viene sin timezone, asumir UTC
            now = now.replace(tzinfo=timezone.utc)
        
        # 2. Normalizar a UTC por si acaso
        now_utc = now.astimezone(timezone.utc)
        current_hour = now_utc.hour
        current_minute = now_utc.minute
        
        # 3. Buscar próximo funding
        for funding_hour in self.funding_hours:
            if current_hour < funding_hour or (current_hour == funding_hour and current_minute < 5):
                # Damos 5 minutos de margen después del funding para considerarlo "pasado"
                return now_utc.replace(hour=funding_hour, minute=0, second=0, microsecond=0)
        
        # 4. Si estamos después de las 16:00, el próximo es mañana 00:00
        tomorrow = now_utc + timedelta(days=1)
        return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)

    def _time_to_next_funding(self, now: datetime = None) -> float:
        """
        Minutos hasta el próximo funding
        """
        next_funding = self._next_funding_time(now)
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        
        now_utc = now.astimezone(timezone.utc)
        return (next_funding - now_utc).total_seconds() / 60
    
   
    def _count_funding_cycles(self, entry_time: datetime, exit_time: datetime = None) -> int:
        """Cuenta cuántos pagos de funding ocurrieron entre entry y exit"""
        # 1. Normalizar ambos tiempos a UTC
        if exit_time is None:
            exit_time = datetime.now(timezone.utc)
        elif exit_time.tzinfo is None:
            exit_time = exit_time.replace(tzinfo=timezone.utc)
        
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        
        # Asegurar que ambos estén en UTC
        entry_utc = entry_time.astimezone(timezone.utc)
        exit_utc = exit_time.astimezone(timezone.utc)
        
        cycles = 0
        # Empezar desde la hora exacta de entrada
        current = entry_utc.replace(minute=0, second=0, microsecond=0)
        
        # Avanzar hora por hora hasta exit_time
        while current < exit_utc:
            if current.hour in self.funding_hours:
                # El funding se paga al INICIO de la hora (00:00, 08:00, 16:00)
                # Para capturarlo, debemos estar en posición ANTES de esa hora
                funding_time = current.replace(minute=0, second=0, microsecond=0)
                
                # Estuvimos en posición durante el snapshot del funding?
                if entry_utc < funding_time and exit_utc > funding_time:
                    cycles += 1
                    logger.debug(f"✅ Ciclo capturado: {funding_time.strftime('%H:%M UTC')}")
            
            current += timedelta(hours=1)
        
        return cycles

    
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

    def register_position(self, symbol: str, side: str, entry_rate: float, size_usd: float, entry_price: float = None):
        self.positions[symbol] = {
            'side': side.lower(),
            'entry_rate': entry_rate,
            'entry_price': entry_price,  # NUEVO
            'entry_time': datetime.now(timezone.utc),
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
    
"""
if __name__ == "__main__":
    # Test de timezone y cálculo de funding
    from datetime import timezone
    
    print("=" * 50)
    print("TEST: Sistema de cálculo de funding")
    print("=" * 50)
    
    strategy = FundingArbitrageStrategy({
        'symbols': ['BTC/USDT'],
        'min_funding_rate': 0.0001,
        'exit_funding_rate': 0.00005,
        'max_position_size_usd': 100,
        'leverage': 5,
        'max_positions': 3
    })
    
    # Test 1: 06:25 UTC (caso del bug - debe retornar 08:00)
    test_time = datetime(2026, 2, 12, 6, 25, 0, tzinfo=timezone.utc)
    next_funding = strategy._next_funding_time(test_time)
    mins = strategy._time_to_next_funding(test_time)
    
    print(f"\n🧪 Test 1 - Entrada a las 06:25 UTC:")
    print(f"   Próximo funding calculado: {next_funding.strftime('%H:%M UTC')}")
    print(f"   Minutos hasta funding: {mins:.0f}")
    print(f"   Esperado: 08:00 UTC (95 minutos)")
    
    if next_funding.hour == 8 and abs(mins - 95) < 1:
        print("   ✅ PASS")
    else:
        print("   ❌ FAIL - Esto explica el bug!")
        print(f"   ⚠️  El bot pensó que faltaban {mins:.0f} min para {next_funding.strftime('%H:%M')}")
    
    # Test 2: 07:55 UTC (justo antes del funding)
    test_time2 = datetime(2026, 2, 12, 7, 55, 0, tzinfo=timezone.utc)
    next_funding2 = strategy._next_funding_time(test_time2)
    mins2 = strategy._time_to_next_funding(test_time2)
    
    print(f"\n🧪 Test 2 - 07:55 UTC (5 min antes del funding):")
    print(f"   Próximo funding: {next_funding2.strftime('%H:%M UTC')}")
    print(f"   Minutos: {mins2:.0f}")
    print(f"   Esperado: 08:00 UTC (5 minutos)")
    print("   ✅ PASS" if next_funding2.hour == 8 and abs(mins2 - 5) < 1 else "   ❌ FAIL")
    
    # Test 3: 08:05 UTC (justo después del funding)
    test_time3 = datetime(2026, 2, 12, 8, 5, 0, tzinfo=timezone.utc)
    next_funding3 = strategy._next_funding_time(test_time3)
    mins3 = strategy._time_to_next_funding(test_time3)
    
    print(f"\n🧪 Test 3 - 08:05 UTC (5 min después del funding):")
    print(f"   Próximo funding: {next_funding3.strftime('%H:%M UTC')}")
    print(f"   Minutos: {mins3:.0f}")
    print(f"   Esperado: 16:00 UTC (475 minutos)")
    print("   ✅ PASS" if next_funding3.hour == 16 and abs(mins3 - 475) < 1 else "   ❌ FAIL")
    
    # Test 4: Hora actual del servidor
    now = datetime.now(timezone.utc)
    next_funding_now = strategy._next_funding_time(now)
    mins_now = strategy._time_to_next_funding(now)
    
    print(f"\n🧪 Test 4 - Hora actual del servidor:")
    print(f"   Hora servidor: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"   Próximo funding: {next_funding_now.strftime('%H:%M UTC')}")
    print(f"   Minutos restantes: {mins_now:.0f}")

    # Test 5: Conteo de ciclos de funding
    print(f"\n🧪 Test 5 - Conteo de ciclos capturados:")
    
    # Caso 1: Entrada 06:25, salida 09:30 (debería capturar 1 ciclo: 08:00)
    entry1 = datetime(2026, 2, 12, 6, 25, 0, tzinfo=timezone.utc)
    exit1 = datetime(2026, 2, 12, 9, 30, 0, tzinfo=timezone.utc)
    cycles1 = strategy._count_funding_cycles(entry1, exit1)
    print(f"   Entrada 06:25, Salida 09:30 → Ciclos: {cycles1} (Esperado: 1)")
    print("   ✅ PASS" if cycles1 == 1 else f"   ❌ FAIL - Esto es el bug del trade de ADA!")
    
    # Caso 2: Entrada 06:25, salida 07:30 (debería capturar 0 ciclos)
    entry2 = datetime(2026, 2, 12, 6, 25, 0, tzinfo=timezone.utc)
    exit2 = datetime(2026, 2, 12, 7, 30, 0, tzinfo=timezone.utc)
    cycles2 = strategy._count_funding_cycles(entry2, exit2)
    print(f"   Entrada 06:25, Salida 07:30 → Ciclos: {cycles2} (Esperado: 0)")
    print("   ✅ PASS" if cycles2 == 0 else "   ❌ FAIL")
    
    # Caso 3: Entrada 06:25, salida 17:00 (debería capturar 2 ciclos: 08:00 y 16:00)
    entry3 = datetime(2026, 2, 12, 6, 25, 0, tzinfo=timezone.utc)
    exit3 = datetime(2026, 2, 12, 17, 0, 0, tzinfo=timezone.utc)
    cycles3 = strategy._count_funding_cycles(entry3, exit3)
    print(f"   Entrada 06:25, Salida 17:00 → Ciclos: {cycles3} (Esperado: 2)")
    print("   ✅ PASS" if cycles3 == 2 else "   ❌ FAIL")
    
    print("\n" + "=" * 50) """