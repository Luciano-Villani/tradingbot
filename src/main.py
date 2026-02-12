import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

# Configuración de rutas
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / "config" / ".env")

from src.logger_config import setup_logger
from src.exchange_client import BinanceClient
from src.funding_strategy import FundingArbitrageStrategy, FundingSignal
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
            config_path = BASE_DIR / "config" / "settings.json"
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Error crítico cargando settings.json: {e}")
            sys.exit(1)
    
    async def initialize(self) -> bool:
        """Inicialización completa y sincronizada del bot"""
        self.start_time = datetime.now()
        
        # 1. Cliente de Exchange
        self.client = BinanceClient(paper_mode=self.paper_mode)
        if not self.client.load_markets():
            print("❌ Error crítico: No se pudo conectar con Binance")
            return False
        
        # 2. Estrategia y Riesgo
        strategy_cfg = self.config.get('strategy', {})
        self.strategy = FundingArbitrageStrategy(strategy_cfg)
        self.risk = RiskManager(self.config.get('risk', {}))
        self.opp_logger = OpportunityLogger()
        
        # 3. Dashboard
        self.dashboard = Dashboard()
        self.dashboard.add_message("🚀 Iniciando ArgenFunding Bot v2.0...")
        
        # Limpieza inicial de pares en el Dashboard
        if self.strategy.symbols:
            for symbol in self.strategy.symbols:
                self.dashboard.update_symbol(symbol, 0.0, "INICIALIZANDO...")
        
        # 4. Sincronizar balance
        try:
            balance_simple = self.client.fetch_balance_simple()
            if balance_simple:
                self.dashboard.update_balance(balance_simple)
                usdt_val = balance_simple.get('USDT', 0)
                self.dashboard.add_message(f"💰 Balance inicial: ${usdt_val:,.2f} USDT")
        except Exception as e:
            self.dashboard.add_message(f"⚠️ Error balance: {str(e)[:30]}")
        
        self.dashboard.add_message(f"✅ Sistema sincronizado: {len(self.strategy.symbols)} pares.")
        self.dashboard.render()
        return True
    
    async def run(self):
        self.running = True
        symbols = self.strategy.symbols 
        
        while self.running:
            self.cycle_count += 1
            try:
                await self._execute_cycle_multi(symbols)
                
            except KeyboardInterrupt:
                await self._graceful_shutdown()
                break
            except Exception as e:
                logger.error(f"Error de ciclo: {e}")
                self.dashboard.add_message(f"⚠️ Error: {str(e)[:40]}")
                await asyncio.sleep(10)
            
            wait_time = self.config['strategy'].get('check_interval_seconds', 60)
            await asyncio.sleep(wait_time)
            
            if self.cycle_count % 60 == 0:
                self.opp_logger.save_daily_summary()
    
    async def _execute_cycle_multi(self, symbols: List[str]):
        """Procesa cada par, gestiona entradas/salidas y actualiza UI"""
        
        if not self.risk.can_trade():
            self.dashboard.add_message("⏸️ Trading pausado por riesgo")
            self.dashboard.render()
            return
        
        balance_simple = self.client.fetch_balance_simple()
        available_usdt = balance_simple.get('USDT', 0)
        
        self.dashboard.update_balance(balance_simple)
        self.dashboard.update_pnl(self.opp_logger.pnl_today)
        
        for symbol in symbols:
            funding = self.client.fetch_funding_rate(symbol)
            ticker = self.client.fetch_ticker(symbol)
            
            if not funding or not ticker:
                continue
            
            # La estrategia decide: open_long, open_short, close o None
            signal = self.strategy.update(symbol, funding, ticker)
            
            if signal:
                # NUEVO: Loguear oportunidad detectada
                mins_to_funding = self.strategy._time_to_next_funding() if hasattr(self.strategy, '_time_to_next_funding') else 0
                
                should_execute = False
                if signal.action == 'close':
                    should_execute = True
                else:
                    should_execute = self._should_execute_entry(signal, available_usdt)
                
                self.opp_logger.log_opportunity(
                    symbol=signal.symbol,
                    funding_rate=signal.funding_rate,
                    mark_price=signal.mark_price,
                    action=signal.action,
                    confidence=signal.confidence,
                    expected_profit_bps=signal.expected_profit_bps,
                    executed=should_execute,
                    next_funding_time=signal.next_funding_time,
                    mins_to_funding=mins_to_funding
                )
                
                # ACCIÓN: CERRAR
                if signal.action == 'close':
                    await self._execute_close(signal)
                
                # ACCIÓN: ABRIR
                elif should_execute:
                    success = await self._execute_entry(signal, available_usdt)
                    if success:
                        # Actualizar disponible local para el siguiente par del ciclo
                        size_full = self.strategy.calculate_size(signal.confidence, available_usdt)
                        available_usdt -= (size_full / self.strategy.leverage)
            else:
                # Sin señal: Solo actualizamos el precio/tasa en el monitor
                self.dashboard.update_symbol(symbol, funding['fundingRate'], "MONITOREANDO")
            
            await asyncio.sleep(0.1) 

        # Sincronizar Dashboard con los datos de hold y ciclos capturados
        self.dashboard.update_positions(self.strategy.get_positions_for_dashboard())
        self.dashboard.render()

    def _should_execute_entry(self, signal: FundingSignal, available_usdt: float) -> bool:
        """Validaciones finales de seguridad"""
        if signal.symbol in self.strategy.get_active_positions(): return False
        if self.strategy.get_position_count() >= self.strategy.max_positions: return False
        
        size = self.strategy.calculate_size(signal.confidence, available_usdt)
        return size >= 15.0 # Mínimo funcional para Binance

    async def _execute_entry(self, signal: FundingSignal, available_usdt: float) -> bool:
        """Envía orden de apertura al exchange"""
        size_usd = self.strategy.calculate_size(signal.confidence, available_usdt)
        amount_crypto = size_usd / signal.mark_price
        side = 'sell' if 'short' in signal.action else 'buy'
        
        order = self.client.create_order(
            symbol=signal.symbol,
            side=side,
            amount=amount_crypto,
            price=signal.mark_price,
            order_type='market'
        )
        
        if order:
            # NUEVO: Guardar entry_price para cálculo de PnL real
            self.strategy.register_position(
                signal.symbol, 
                'short' if side == 'sell' else 'long', 
                signal.funding_rate, 
                size_usd,
                signal.mark_price  # NUEVO: entry_price
            )
            self.opp_logger.log_trade_entry(
                symbol=signal.symbol,
                action=signal.action,
                size_usd=size_usd,
                entry_price=signal.mark_price,
                funding_rate=signal.funding_rate,
                next_funding_time=signal.next_funding_time
            )
            self.dashboard.add_message(f"✅ ABIERTO: {signal.symbol} {signal.action}")
            return True
        return False

    async def _execute_close(self, signal: FundingSignal):
        """Envía orden de cierre y guarda métricas de ciclos capturados"""
        metrics = self.strategy.get_position_metrics(signal.symbol)
        pos_info = self.strategy.positions.get(signal.symbol)
        if not pos_info: return
        
        side_to_close = 'buy' if pos_info['side'] == 'short' else 'sell'
        amount_crypto = pos_info['size_usd'] / signal.mark_price
        
        order = self.client.create_order(
            symbol=signal.symbol,
            side=side_to_close,
            amount=amount_crypto,
            price=signal.mark_price,
            order_type='market'
        )
        
        if order:
            # NUEVO: Calcular PnL real (precio + funding)
            entry_price = pos_info.get('entry_price', signal.mark_price)
            exit_price = signal.mark_price
            size_usd = pos_info['size_usd']
            leverage = self.strategy.leverage
            
            # PnL por movimiento de precio
            if pos_info['side'] == 'short':
                price_pnl = (entry_price - exit_price) / entry_price * size_usd * leverage
            else:
                price_pnl = (exit_price - entry_price) / entry_price * size_usd * leverage
            
            # PnL por funding capturado
            funding_pnl = size_usd * abs(pos_info['entry_rate']) * metrics['cycles_captured']
            
            pnl_total = price_pnl + funding_pnl
            
            self.opp_logger.log_trade_exit(
                symbol=signal.symbol,
                exit_price=signal.mark_price,
                pnl_usd=pnl_total,
                cycles_captured=metrics['cycles_captured'],
                hold_hours=metrics['hold_hours']
            )
            
            self.strategy.clear_position(signal.symbol)
            self.dashboard.add_message(f"🚪 CERRADO: {signal.symbol} | Ciclos: {metrics['cycles_captured']} | PnL: ${pnl_total:.2f}")

    async def _graceful_shutdown(self):
        self.running = False
        self.dashboard.add_message("🛑 Apagando sistema...")
        if self.opp_logger:
            self.opp_logger.save_daily_summary()
        self.dashboard.render()
        print("\n[!] Bot detenido correctamente.")

async def main():
    bot = ArgenFundingBot()
    try:
        initialized = await bot.initialize()
        if initialized:
            await bot.run()
    except Exception as e:
        logger.exception(f"Error fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
    