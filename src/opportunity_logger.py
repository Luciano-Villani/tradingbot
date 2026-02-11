import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

class OpportunityLogger:
    """Registra oportunidades detectadas y trades ejecutados"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.opportunities_file = self.data_dir / "opportunities.csv"
        self.trades_file = self.data_dir / "trades_executed.csv"
        self.daily_summary_file = self.data_dir / "daily_summary.json"
        
        self.opportunities_today = 0
        self.trades_today = 0
        self.pnl_today = 0.0
        
        self._init_files()
    
    def _init_files(self):
        """Crea archivos con headers si no existen"""
        
        if not self.opportunities_file.exists():
            with open(self.opportunities_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'funding_rate', 'mark_price',
                    'action', 'confidence', 'expected_profit_bps', 'executed'
                ])
        
        if not self.trades_file.exists():
            with open(self.trades_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'action', 'size_usd', 'entry_price',
                    'funding_rate', 'exit_timestamp', 'exit_price', 'pnl_usd', 'status'
                ])
    
    def log_opportunity(self, symbol: str, funding_rate: float, mark_price: float,
                       action: str, confidence: float, expected_profit_bps: float,
                       executed: bool = False):
        """Registra una oportunidad detectada"""
        
        self.opportunities_today += 1
        
        with open(self.opportunities_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                symbol,
                f"{funding_rate:.6f}",
                f"{mark_price:.2f}",
                action,
                f"{confidence:.2f}",
                f"{expected_profit_bps:.2f}",
                "YES" if executed else "NO"
            ])
        
        return executed
    
    def log_trade_entry(self, symbol: str, action: str, size_usd: float,
                       entry_price: float, funding_rate: float) -> str:
        """Registra apertura de trade"""
        
        self.trades_today += 1
        
        with open(self.trades_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                symbol,
                action,
                f"{size_usd:.2f}",
                f"{entry_price:.2f}",
                f"{funding_rate:.6f}",
                "",
                "",
                "",
                "OPEN"
            ])
        
        return f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def log_trade_exit(self, symbol: str, exit_price: float, pnl_usd: float):
        """Registra cierre de trade"""
        
        self.pnl_today += pnl_usd
        
        rows = []
        with open(self.trades_file, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            rows.append(header)
            
            for row in reader:
                if len(row) >= 6 and row[1] == symbol and row[10] == "OPEN":
                    row[6] = datetime.now().isoformat()
                    row[7] = f"{exit_price:.2f}"
                    row[8] = f"{pnl_usd:.2f}"
                    row[10] = "CLOSED"
                rows.append(row)
        
        with open(self.trades_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    
    def save_daily_summary(self):
        """Guarda resumen del día"""
        
        summary = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'opportunities_detected': self.opportunities_today,
            'trades_executed': self.trades_today,
            'pnl_usd': round(self.pnl_today, 2),
            'timestamp': datetime.now().isoformat()
        }
        
        summaries = []
        if self.daily_summary_file.exists():
            try:
                with open(self.daily_summary_file, 'r') as f:
                    summaries = json.load(f)
                    if not isinstance(summaries, list):
                        summaries = [summaries]
            except:
                summaries = []
        
        summaries = [s for s in summaries if s.get('date') != summary['date']]
        summaries.append(summary)
        
        with open(self.daily_summary_file, 'w') as f:
            json.dump(summaries, f, indent=2)
    
    def get_stats(self) -> Dict:
        """Retorna estadísticas actuales"""
        return {
            'opportunities_today': self.opportunities_today,
            'trades_today': self.trades_today,
            'pnl_today': self.pnl_today,
            'open_trades': self._count_open_trades()
        }
    
    def _count_open_trades(self) -> int:
        """Cuenta trades abiertos"""
        count = 0
        try:
            with open(self.trades_file, 'r') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    if len(row) > 10 and row[10] == "OPEN":
                        count += 1
        except:
            pass
        return count