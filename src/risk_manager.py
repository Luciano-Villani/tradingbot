from datetime import datetime, timedelta
from typing import Dict
from loguru import logger

class RiskManager:
    def __init__(self, config: Dict):
        self.max_daily_loss = config.get('max_daily_loss_usd', 50)
        self.max_positions = config.get('max_positions', 1)
        self.max_errors = config.get('max_errors_per_day', 10)
        self.auto_stop = config.get('auto_stop_on_errors', True)
        
        self.daily_stats = {
            'date': datetime.now().date(),
            'pnl': 0.0,
            'trades': 0,
            'errors': 0,
            'positions_opened': 0
        }
        self.emergency_stop = False
        self.last_check = datetime.now()
    
    def can_trade(self) -> bool:
        self._reset_if_new_day()
        
        if self.emergency_stop:
            logger.critical("EMERGENCY STOP activo")
            return False
        
        if self.daily_stats['errors'] >= self.max_errors:
            logger.critical(f"Máximo errores: {self.daily_stats['errors']}")
            if self.auto_stop:
                self.emergency_stop = True
            return False
        
        if self.daily_stats['pnl'] <= -self.max_daily_loss:
            logger.critical(f"Pérdida máxima: ${self.daily_stats['pnl']:.2f}")
            return False
        
        return True
    
    def _reset_if_new_day(self):
        today = datetime.now().date()
        if today != self.daily_stats['date']:
            logger.info(f"Nuevo día. Ayer P&L: ${self.daily_stats['pnl']:.2f}")
            self.daily_stats = {
                'date': today,
                'pnl': 0.0,
                'trades': 0,
                'errors': 0,
                'positions_opened': 0
            }
            self.emergency_stop = False
    
    def register_trade(self, pnl: float):
        self.daily_stats['pnl'] += pnl
        self.daily_stats['trades'] += 1
        logger.info(f"Trade P&L: ${pnl:.2f} | Diario: ${self.daily_stats['pnl']:.2f}")
    
    def register_error(self, critical: bool = False):
        self.daily_stats['errors'] += 1
        if critical:
            logger.critical(f"Error crítico #{self.daily_stats['errors']}")
            self.emergency_stop = True
        else:
            logger.warning(f"Error #{self.daily_stats['errors']}/{self.max_errors}")
    
    def register_position_opened(self):
        self.daily_stats['positions_opened'] += 1
    
    def get_status(self) -> Dict:
        return {
            'date': str(self.daily_stats['date']),
            'pnl_usd': round(self.daily_stats['pnl'], 2),
            'trades': self.daily_stats['trades'],
            'errors': self.daily_stats['errors'],
            'emergency_stop': self.emergency_stop,
            'can_trade': self.can_trade()
        }
    
    def manual_stop(self):
        self.emergency_stop = True
        logger.critical("STOP MANUAL activado")
    
    def manual_reset(self):
        self.emergency_stop = False
        self.daily_stats['errors'] = 0
        logger.warning("RESET MANUAL ejecutado")

