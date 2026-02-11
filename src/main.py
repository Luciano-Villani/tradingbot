import os
import sys
import json
import asyncio
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / "config" / ".env")

from src.logger_config import setup_logger
from src.exchange_client import BinanceClient
from src.funding_strategy import FundingArbitrageStrategy
from src.risk_manager import RiskManager
from src.opportunity_logger import OpportunityLogger
from src.dashboard import Dashboard

logger = setup_logger(BASE_DIR / "config" / "settings.json")

class ArgenFundingBot:
    def __init__(self):
        self.config = self._load_config()
        self.paper_mode = os.getenv('PAPER_MODE', 'true').lower() == 'true'
        
        self.client: BinanceClient = None
        self.strategy: FundingArbitrageStrategy = None
        self.risk: RiskManager = None
        self.opp_logger: OpportunityLogger = None
        self.dashboard: Dashboard = None
        
        self.running = False
        self.cycle_count = 0
        self.start_time = None
        
    def _load_config(self) -> Dict:
        try:
            with open(BASE_DIR / "config" / "settings.json") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando config: {e}")
            return {}
    
    async def initialize(self) -> bool:
        # Inicializar dashboard primero
        self.dashboard = Dashboard()
        self.dashboard.add_message("Iniciando bot...")
        self.dashboard.render()
        
        self.start_time = datetime.now()
        
        self.client = BinanceClient(paper_mode=self.paper_mode)
        if not self.client.load_markets():
            self.dashboard.add_message("❌ Error cargando mercados")
            return False
        
        balance = self.client.fetch_balance()
        if not balance:
            self.dashboard.add_message("❌ Error obteniendo balance")
            return False
        
        # Actualizar dashboard con balance
        balance_simple = self.client.fetch_balance_simple()
        self.dashboard.update_balance(balance_simple)
        self.dashboard.add_message(f"Balance cargado: ${balance_simple['USDT']:,.2f} USDT")
        
        self.strategy = FundingArbitrageStrategy(self.config['strategy'])
        self.risk = RiskManager(self.config['risk'])
        self.opp_logger = OpportunityLogger()
        
        self.dashboard.add_message(f"✅ Bot listo - {len(self.config['strategy']['symbols'])} pares")
        return True
    
    async def run(self):
        self.running = True
        symbols = self.config['strategy']['symbols']
        
        self.dashboard.add_message(f"Monitoreando {len(symbols)} pares...")
        
        while self.running:
            self.cycle_count += 1
            
            try:
                await self._execute_cycle_multi(symbols)
                
            except KeyboardInterrupt:
                self.dashboard.add_message("⛔ Detenido por usuario")
                await self._graceful_shutdown()
                break
                
            except Exception as e:
                self.dashboard.add_message(f"❌ Error: {str(e)[:50]}")
                self.risk.register_error(critical=True)
                await asyncio.sleep(60)
            
            # Controlar frecuencia
            await asyncio.sleep(self.config['strategy']['check_interval_seconds'])
            
            # Guardar resumen cada hora
            if self.cycle_count % 120 == 0:
                self.opp_logger.save_daily_summary()
    
    async def _execute_cycle_multi(self, symbols: List[str]):
        """Ejecuta ciclo para múltiples pares"""
        
        if not self.risk.can_trade():
            self.dashboard.add_message("⏸️ Trading pausado por riesgo")
            self.dashboard.render()
            return
        
        # Obtener balance
        balance_simple = self.client.fetch_balance_simple()
        available_usdt = balance_simple['USDT']
        self.dashboard.update_balance(balance_simple)
        
        # Scanear cada par
        for symbol in symbols:
            funding = self.client.fetch_funding_rate(symbol)
            ticker = self.client.fetch_ticker(symbol)
            
            if not funding or not ticker:
                self.dashboard.update_symbol(symbol, 0, "ERROR DATOS")
                continue
            
            # Evaluar señal
            signal = self.strategy.update(symbol, funding, ticker)
            
            if signal:
                self.dashboard.increment_opportunities()
                
                # Determinar si ejecutar
                should_execute = self._should_execute(signal, available_usdt)
                
                # Loguear oportunidad
                self.opp_logger.log_opportunity(
                    symbol=signal.symbol,
                    funding_rate=signal.funding_rate,
                    mark_price=signal.mark_price,
                    action=signal.action,
                    confidence=signal.confidence,
                    expected_profit_bps=signal.expected_profit_bps,
                    executed=should_execute
                )
                
                # Actualizar dashboard
                status = "EJECUTANDO" if should_execute else "DETECTADA"
                self.dashboard.update_symbol(symbol, signal.funding_rate, f"{status}: {signal.action}")
                self.dashboard.add_message(f"🎯 {symbol} {signal.action} | Funding: {signal.funding_rate:.4%}")
                
                # Ejecutar si corresponde
                if should_execute:
                    success = await self._execute_signal(signal, available_usdt)
                    if success:
                        available_usdt -= self.strategy.calculate_size(signal.confidence, available_usdt)
            else:
                # Sin señal, mostrar funding actual
                self.dashboard.update_symbol(symbol, funding['fundingRate'], "MONITOREANDO")
            
            await asyncio.sleep(0.1)
        
        # Actualizar posiciones en dashboard
        self.dashboard.update_positions(self.strategy.get_positions_for_dashboard())
        self.dashboard.update_pnl(self.opp_logger.get_stats()['pnl_today'])
        self.dashboard.render()
    
    def _should_execute(self, signal: FundingSignal, available_usdt: float) -> bool:
        """Determina si ejecutar una señal"""
        
        size = self.strategy.calculate_size(signal.confidence, available_usdt)
        if size < 10:
            return False
        
        if signal.symbol in self.strategy.get_active_positions():
            return False
        
        if self.strategy.get_position_count() >= self.config['strategy']['max_positions']:
            return False
        
        return True
    
    async def _execute_signal(self, signal: FundingSignal, available_usdt: float) -> bool:
        """Ejecuta señal de trading"""
        
        size_usd = self.strategy.calculate_size(signal.confidence, available_usdt)
        if size_usd < 10:
            return False
        
        btc_amount = (size_usd * self.config['strategy']['leverage']) / signal.mark_price
        side = 'sell' if signal.action == 'open_short' else 'buy'
        
        order = self.client.create_order(
            symbol=signal.symbol,
            side=side,
            amount=btc_amount,
            price=signal.mark_price * (0.999 if side == 'buy' else 1.001),
            order_type='limit'
        )
        
        if order:
            position_side = 'short' if signal.action == 'open_short' else 'long'
            self.strategy.register_position(signal.symbol, position_side, signal.funding_rate, size_usd)
            
            self.opp_logger.log_trade_entry(
                symbol=signal.symbol,
                action=signal.action,
                size_usd=size_usd,
                entry_price=signal.mark_price,
                funding_rate=signal.funding_rate
            )
            
            self.risk.register_position_opened()
            self.dashboard.add_message(f"✅ ORDEN EXECUTADA: {signal.symbol} {signal.action}")
            return True
        
        return False
    
    async def _graceful_shutdown(self):
        """Cierre ordenado"""
        self.dashboard.add_message("Cerrando bot...")
        self.running = False
        
        if self.opp_logger:
            self.opp_logger.save_daily_summary()
        
        active = self.strategy.get_active_positions() if self.strategy else []
        for symbol in active:
            self.client.close_position(symbol)
        
        self.dashboard.render()
        print("\nBot detenido. Presiona Enter para salir...")
        input()

def main():
    bot = ArgenFundingBot()
    try:
        if asyncio.run(bot.initialize()):
            asyncio.run(bot.run())
    except Exception as e:
        print(f"Error fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
    