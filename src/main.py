import os
import sys
import json
import asyncio
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / "config" / ".env")

from src.logger_config import setup_logger
from src.exchange_client import BinanceClient
from src.funding_strategy import FundingArbitrageStrategy
from src.risk_manager import RiskManager

logger = setup_logger(BASE_DIR / "config" / "settings.json")

class ArgenFundingBot:
    def __init__(self):
        self.config = self._load_config()
        self.paper_mode = os.getenv('PAPER_MODE', 'true').lower() == 'true'
        self.client = None
        self.strategy = None
        self.risk = None
        self.running = False
        self.cycle_count = 0
        self.start_time = None
        
    def _load_config(self):
        try:
            with open(BASE_DIR / "config" / "settings.json") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error config: {e}")
            return {}
    
    async def initialize(self) -> bool:
        logger.info("="*60)
        logger.info("ARGENFUNDING BOT v1.0 - Argentina Optimized")
        logger.info(f"Inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Paper Mode: {self.paper_mode}")
        logger.info("="*60)
        
        self.client = BinanceClient(paper_mode=self.paper_mode)
        if not self.client.load_markets():
            return False
        
        balance = self.client.fetch_balance()
        if not balance:
            return False
        
        logger.info(f"Balance: ${balance['free']:.2f} USDT disponible")
        
        self.strategy = FundingArbitrageStrategy(self.config['strategy'])
        self.risk = RiskManager(self.config['risk'])
        self.start_time = datetime.now()
        return True
    
    async def run(self):
        self.running = True
        while self.running:
            self.cycle_count += 1
            cycle_start = time.time()
            
            try:
                await self._execute_cycle()
            except KeyboardInterrupt:
                logger.info("Interrupción usuario")
                await self._graceful_shutdown()
                break
            except Exception as e:
                logger.exception(f"Error crítico: {e}")
                self.risk.register_error(critical=True)
                await asyncio.sleep(60)
            
            elapsed = time.time() - cycle_start
            sleep_time = max(0, self.config['strategy']['check_interval_seconds'] - elapsed)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    
    async def _execute_cycle(self):
        if not self.risk.can_trade():
            if self.cycle_count % 10 == 0:
                logger.warning("Trading pausado por riesgo")
            return
        
        funding = self.client.fetch_funding_rate(self.config['strategy']['symbol'])
        ticker = self.client.fetch_ticker(self.config['strategy']['symbol'])
        
        if not funding or not ticker:
            self.risk.register_error()
            return
        
        signal = self.strategy.update(funding, ticker)
        
        if signal:
            await self._execute_signal(signal)
        
        if self.cycle_count % 20 == 0:
            self._log_status(funding, ticker)
    
    async def _execute_signal(self, signal):
        if signal.action in ['open_short', 'open_long']:
            if self.strategy.position:
                return
            
            self.risk.register_position_opened()
            balance = self.client.fetch_balance()
            if not balance:
                return
            
            size_usd = self.strategy.calculate_size(signal.confidence, balance['free'])
            if size_usd < 10:
                return
            
            btc_amount = (size_usd * self.config['strategy']['leverage']) / signal.mark_price
            side = 'sell' if signal.action == 'open_short' else 'buy'
            
            order = self.client.create_order(
                symbol=signal.symbol,
                side=side,
                amount=btc_amount,
                price=signal.mark_price * (0.999 if side == 'buy' else 1.001),
                order_type='limit',
                params={'leverage': self.config['strategy']['leverage']}
            )
            
            if order:
                self.strategy.register_position(
                    'short' if signal.action == 'open_short' else 'long',
                    signal.funding_rate
                )
                logger.info(f"TRADE,OPEN,{signal.action},{size_usd},{signal.mark_price},{signal.funding_rate}")
        
        elif signal.action == 'close':
            if self.client.close_position(signal.symbol):
                pnl = 0.5 if self.paper_mode else 0  # Simplificado
                self.risk.register_trade(pnl)
                self.strategy.clear_position()
                logger.info(f"TRADE,CLOSE,,,{pnl},")
        
        elif signal.action == 'close_and_reverse':
            if self.client.close_position(signal.symbol):
                pnl = 0.5 if self.paper_mode else 0
                self.risk.register_trade(pnl)
                self.strategy.clear_position()
                logger.info(f"TRADE,CLOSE_REVERSE,,,{pnl},")
                await asyncio.sleep(5)
    
    def _log_status(self, funding: Dict, ticker: Dict):
        uptime = datetime.now() - self.start_time
        risk_status = self.risk.get_status()
        logger.info(
            f"Status | Ciclos: {self.cycle_count} | "
            f"Uptime: {uptime} | "
            f"Funding: {funding['fundingRate']:.4%} | "
            f"Price: ${ticker['last']:,.2f} | "
            f"P&L: ${risk_status['pnl_usd']:.2f}"
        )
    
    async def _graceful_shutdown(self):
        logger.info("Cerrando bot...")
        self.running = False
        if self.strategy and self.strategy.position:
            self.client.close_position(self.config['strategy']['symbol'])
        uptime = datetime.now() - self.start_time
        logger.info(f"Bot detenido. Uptime: {uptime}")

def main():
    bot = ArgenFundingBot()
    try:
        if asyncio.run(bot.initialize()):
            asyncio.run(bot.run())
    except Exception as e:
        logger.exception(f"Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

