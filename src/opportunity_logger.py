import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

class OpportunityLogger:
    """Registra oportunidades detectadas y trades ejecutados con métricas de funding"""
    
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
                    'action', 'confidence', 'expected_profit_bps', 'executed',
                    'next_funding_time', 'mins_to_funding'  # NUEVOS
                ])
        
        if not self.trades_file.exists():
            with open(self.trades_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'symbol', 'action', 'size_usd', 'entry_price',
                    'funding_rate', 'next_funding_time',  # NUEVO
                    'exit_timestamp', 'exit_price', 'pnl_usd', 
                    'cycles_captured', 'hold_hours',  # NUEVOS
                    'status'
                ])
    
    def log_opportunity(self, symbol: str, funding_rate: float, mark_price: float,
                       action: str, confidence: float, expected_profit_bps: float,
                       executed: bool = False, next_funding_time: datetime = None,
                       mins_to_funding: float = 0):
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
                "YES" if executed else "NO",
                next_funding_time.isoformat() if next_funding_time else "",
                f"{mins_to_funding:.0f}"
            ])
        
        return executed
    
    def log_trade_entry(self, symbol: str, action: str, size_usd: float,
                       entry_price: float, funding_rate: float,
                       next_funding_time: datetime = None) -> str:
        """Registra apertura de trade con timing de funding"""
        
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
                next_funding_time.isoformat() if next_funding_time else "",
                "",  # exit_timestamp
                "",  # exit_price
                "",  # pnl_usd
                "",  # cycles_captured
                "",  # hold_hours
                "OPEN"
            ])
        
        return f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def log_trade_exit(self, symbol: str, exit_price: float, pnl_usd: float,
                      cycles_captured: int = 0, hold_hours: float = 0):
        """Registra cierre de trade con métricas de funding"""
        
        self.pnl_today += pnl_usd
        
        rows = []
        with open(self.trades_file, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            rows.append(header)
            
            for row in reader:
                # Buscar el trade abierto más reciente para este símbolo
                if len(row) >= 6 and row[1] == symbol and row[12] == "OPEN":
                    row[7] = datetime.now().isoformat()  # exit_timestamp
                    row[8] = f"{exit_price:.2f}"
                    row[9] = f"{pnl_usd:.2f}"
                    row[10] = str(cycles_captured)  # cycles_captured
                    row[11] = f"{hold_hours:.2f}"   # hold_hours
                    row[12] = "CLOSED"
                rows.append(row)
        
        with open(self.trades_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    
    def save_daily_summary(self):
        """Guarda resumen del día con métricas de funding"""
        
        # Calcular métricas adicionales
        avg_hold_time = self._calculate_avg_hold_time()
        avg_cycles = self._calculate_avg_cycles()
        
        summary = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'opportunities_detected': self.opportunities_today,
            'trades_executed': self.trades_today,
            'pnl_usd': round(self.pnl_today, 2),
            'avg_hold_hours': round(avg_hold_time, 2),
            'avg_cycles_captured': round(avg_cycles, 2),
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
            'open_trades': self._count_open_trades(),
            'avg_hold_time': self._calculate_avg_hold_time(),
            'avg_cycles': self._calculate_avg_cycles()
        }
    
    def _count_open_trades(self) -> int:
        """Cuenta trades abiertos"""
        count = 0
        try:
            with open(self.trades_file, 'r') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    if len(row) > 12 and row[12] == "OPEN":
                        count += 1
        except:
            pass
        return count
    
    def _calculate_avg_hold_time(self) -> float:
        """Calcula tiempo promedio en posición (solo trades cerrados hoy)"""
        hold_times = []
        today = datetime.now().strftime('%Y-%m-%d')
        
        try:
            with open(self.trades_file, 'r') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    if len(row) > 11 and row[12] == "CLOSED":
                        entry_date = row[0][:10]
                        if entry_date == today and row[11]:
                            hold_times.append(float(row[11]))
        except:
            pass
        
        return sum(hold_times) / len(hold_times) if hold_times else 0
    
    def _calculate_avg_cycles(self) -> float:
        """Calcula ciclos de funding promedio capturados"""
        cycles_list = []
        today = datetime.now().strftime('%Y-%m-%d')
        
        try:
            with open(self.trades_file, 'r') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    if len(row) > 10 and row[12] == "CLOSED":
                        entry_date = row[0][:10]
                        if entry_date == today and row[10]:
                            cycles_list.append(float(row[10]))
        except:
            pass
        
        return sum(cycles_list) / len(cycles_list) if cycles_list else 0
    
    def get_performance_by_symbol(self) -> Dict:
        """NUEVO: Análisis de performance por par de trading"""
        performance = {}
        
        try:
            with open(self.trades_file, 'r') as f:
                reader = csv.reader(f)
                next(reader)
                for row in reader:
                    if len(row) > 9 and row[12] == "CLOSED":
                        symbol = row[1]
                        pnl = float(row[9]) if row[9] else 0
                        cycles = float(row[10]) if row[10] else 0
                        hold = float(row[11]) if row[11] else 0
                        
                        if symbol not in performance:
                            performance[symbol] = {
                                'trades': 0, 'total_pnl': 0, 
                                'total_cycles': 0, 'total_hold_hours': 0
                            }
                        
                        performance[symbol]['trades'] += 1
                        performance[symbol]['total_pnl'] += pnl
                        performance[symbol]['total_cycles'] += cycles
                        performance[symbol]['total_hold_hours'] += hold
            
            # Calcular promedios
            for symbol in performance:
                trades = performance[symbol]['trades']
                performance[symbol]['avg_pnl'] = round(performance[symbol]['total_pnl'] / trades, 2)
                performance[symbol]['avg_cycles'] = round(performance[symbol]['total_cycles'] / trades, 2)
                performance[symbol]['avg_hold_hours'] = round(performance[symbol]['total_hold_hours'] / trades, 2)
                
        except Exception as e:
            logger.error(f"Error calculando performance: {e}")
        
        return performance
    