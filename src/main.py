import os
import sys
import json
import asyncio
import time
from pathlib import Path
from datetime import datetime
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
        
        # 1. Inicializar Cliente de Exchange
        self.client = BinanceClient(paper_mode=self.paper_mode)
        if not self.client.load_markets():
            print("❌ Error crítico: No se pudo conectar con Binance")
            return False
        
        # 2. Inicializar Estrategia y Riesgo
        # Cargamos la configuración y extraemos los símbolos del JSON
        strategy_cfg = self.config.get('strategy', {})
        self.strategy = FundingArbitrageStrategy(strategy_cfg)
        self.risk = RiskManager(self.config.get('risk', {}))
        self.opp_logger = OpportunityLogger()
        
        # 3. Inicializar Dashboard
        self.dashboard = Dashboard()
        self.dashboard.add_message("🚀 Iniciando ArgenFunding Bot...")
        
        # --- AJUSTE RECOMENDADO: Sincronización Inmediata ---
        # Forzamos al Dashboard a registrar solo tus 8 pares seleccionados
        # Esto resetea cualquier dato viejo de sesiones anteriores.
        if self.strategy.symbols:
            for symbol in self.strategy.symbols:
                self.dashboard.update_symbol(symbol, 0.0, "INICIALIZANDO...")
        else:
            self.dashboard.add_message("⚠️ Advertencia: No hay símbolos cargados")
            return False

        # 4. Sincronizar balance inicial
        try:
            balance_simple = self.client.fetch_balance_simple()
            if balance_simple:
                self.dashboard.update_balance(balance_simple)
                usdt_val = balance_simple.get('USDT', 0)
                self.dashboard.add_message(f"💰 Balance inicial: ${usdt_val:,.2f} USDT")
        except Exception as e:
            self.dashboard.add_message(f"⚠️ Error balance: {str(e)[:30]}")
        
        # Mensaje final de éxito
        self.dashboard.add_message(f"✅ Sistema sincronizado: {len(self.strategy.symbols)} pares.")
        self.dashboard.render()
        
        return True
    
    async def run(self):
        self.running = True
        # Usamos EXCLUSIVAMENTE los símbolos definidos en la estrategia
        symbols = self.strategy.symbols 
        
        self.dashboard.add_message(f"📡 Monitoreando: {', '.join([s.split('/')[0] for s in symbols])}")
        
        while self.running:
            self.cycle_count += 1
            try:
                await self._execute_cycle_multi(symbols)
                
            except KeyboardInterrupt:
                await self._graceful_shutdown()
                break
            except Exception as e:
                self.dashboard.add_message(f"⚠️ Error en ciclo: {str(e)[:40]}")
                logger.error(f"Error de ciclo: {e}")
                await asyncio.sleep(10)
            
            # Intervalo de chequeo desde JSON
            wait_time = self.config['strategy'].get('check_interval_seconds', 30)
            await asyncio.sleep(wait_time)
            
            # Resumen cada hora
            if self.cycle_count % 120 == 0:
                self.opp_logger.save_daily_summary()
    
    async def _execute_cycle_multi(self, symbols: List[str]):
        """Procesa cada símbolo y actualiza la interfaz"""
        
        if not self.risk.can_trade():
            self.dashboard.add_message("⏸️ Trading pausado por gestión de riesgo")
            self.dashboard.render()
            return
        
        # Actualizar balance en cada ciclo
        balance_simple = self.client.fetch_balance_simple()
        available_usdt = balance_simple.get('USDT', 0)
        self.dashboard.update_balance(balance_simple)
        
        for symbol in symbols:
            # Obtener datos de mercado
            funding = self.client.fetch_funding_rate(symbol)
            ticker = self.client.fetch_ticker(symbol)
            
            if not funding or not ticker:
                self.dashboard.update_symbol(symbol, 0, "Error de Datos")
                continue
            
            # La estrategia decide (ya tiene los filtros de 0.01% aplicados)
            signal = self.strategy.update(symbol, funding, ticker)
            
            if signal:
                self.dashboard.increment_opportunities()
                should_execute = self._should_execute(signal, available_usdt)
                
                # Registrar en log de oportunidades
                self.opp_logger.log_opportunity(
                    symbol=signal.symbol,
                    funding_rate=signal.funding_rate,
                    mark_price=signal.mark_price,
                    action=signal.action,
                    confidence=signal.confidence,
                    expected_profit_bps=signal.expected_profit_bps,
                    executed=should_execute
                )
                
                if should_execute:
                    self.dashboard.update_symbol(symbol, signal.funding_rate, f"EJECUTANDO {signal.action}")
                    success = await self._execute_signal(signal, available_usdt)
                    if success:
                        # Descontar mentalmente para el siguiente par en el mismo ciclo
                        available_usdt -= (self.strategy.calculate_size(signal.confidence, available_usdt) / self.strategy.leverage)
                else:
                    self.dashboard.update_symbol(symbol, signal.funding_rate, f"SEÑAL: {signal.action}")
            else:
                # Si no hay señal, simplemente reportar estado
                self.dashboard.update_symbol(symbol, funding['fundingRate'], "MONITOREANDO")
            
            # Pequeño delay para no saturar la API
            await asyncio.sleep(0.05)
        
        # Refrescar UI al final del ciclo de todos los pares
        self.dashboard.update_positions(self.strategy.get_positions_for_dashboard())
        self.dashboard.update_pnl(self.opp_logger.get_stats().get('pnl_today', 0.0))
        self.dashboard.render()
    
    def _should_execute(self, signal: FundingSignal, available_usdt: float) -> bool:
        """Filtros finales de riesgo antes de disparar orden"""
        size = self.strategy.calculate_size(signal.confidence, available_usdt)
        
        # No operar si el tamaño es insignificante (< $10)
        if size < 10: return False
        
        # No duplicar posiciones en la misma moneda
        if signal.symbol in self.strategy.get_active_positions(): return False
        
        # Respetar el máximo de posiciones simultáneas del JSON
        if self.strategy.get_position_count() >= self.strategy.max_positions: return False
        
        return True
    
    async def _execute_signal(self, signal: FundingSignal, available_usdt: float) -> bool:
        """Envía la orden real/demo al exchange"""
        size_usd = self.strategy.calculate_size(signal.confidence, available_usdt)
        
        # Calcular cantidad en cripto (ej: 0.001 BTC)
        # Recordar: size_usd ya incluye el apalancamiento
        amount_crypto = size_usd / signal.mark_price
        side = 'sell' if 'short' in signal.action else 'buy'
        
        # Ejecutar orden (Limit con ligero offset para asegurar ejecución)
        price_offset = 0.9998 if side == 'buy' else 1.0002
        order = self.client.create_order(
            symbol=signal.symbol,
            side=side,
            amount=amount_crypto,
            price=signal.mark_price * price_offset,
            order_type='limit'
        )
        
        if order:
            pos_side = 'short' if 'short' in signal.action else 'long'
            self.strategy.register_position(signal.symbol, pos_side, signal.funding_rate, size_usd)
            
            self.opp_logger.log_trade_entry(
                symbol=signal.symbol,
                action=signal.action,
                size_usd=size_usd,
                entry_price=signal.mark_price,
                funding_rate=signal.funding_rate
            )
            
            self.risk.register_position_opened()
            self.dashboard.add_message(f"✅ ORDEN OK: {signal.symbol} {signal.action.upper()}")
            return True
        
        return False
    
    async def _graceful_shutdown(self):
        self.running = False
        self.dashboard.add_message("🛑 Apagando sistema de forma segura...")
        
        if self.opp_logger:
            self.opp_logger.save_daily_summary()
        
        # Opcional: Cerrar posiciones al apagar
        # active = self.strategy.get_active_positions()
        # for symbol in active:
        #    self.client.close_position(symbol)
        
        self.dashboard.render()
        print("\n[!] Bot detenido. Sesión finalizada.")

def main():
    bot = ArgenFundingBot()
    try:
        # Inicialización asíncrona
        loop = asyncio.get_event_loop()
        if loop.run_until_complete(bot.initialize()):
            loop.run_until_complete(bot.run())
    except Exception as e:
        print(f"❌ ERROR FATAL: {e}")
        logger.exception("Error fatal en main")
        sys.exit(1)

if __name__ == "__main__":
    main()
