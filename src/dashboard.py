import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List

class Dashboard:
    def __init__(self):
        self.start_time = datetime.now()
        self.symbols_data: Dict[str, Dict] = {}
        self.positions: Dict[str, Dict] = {}
        self.balance = {'USDT': 0, 'USDC': 0}
        self.pnl_today = 0.0
        self.opportunities_count = 0
        self.messages: List[str] = []

    def update_symbol(self, symbol: str, funding_rate: float, signal: str = None):
        self.symbols_data[symbol] = {
            'funding': funding_rate,
            'signal': signal or 'MONITOREANDO',
            'last_update': datetime.now()
        }

    def update_positions(self, positions: Dict):
        """Recibe datos detallados de funding_strategy.get_positions_for_dashboard()"""
        self.positions = positions

    def update_balance(self, balance: Dict):
        self.balance = balance

    def update_pnl(self, pnl: float):
        self.pnl_today = pnl

    def increment_opportunities(self):
        self.opportunities_count += 1

    def add_message(self, msg: str):
        self.messages.append(f"{datetime.now().strftime('%H:%M:%S')} {msg}")
        if len(self.messages) > 5: self.messages.pop(0)

    def render(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        uptime = datetime.now() - self.start_time
        
        # Filtrar solo pares activos
        active_symbols = {
            s: d for s, d in self.symbols_data.items() 
            if d['last_update'] > datetime.now() - timedelta(minutes=5)
        }

        print("╔" + "═" * 78 + "╗")
        print(f"║{'ARGENFUNDING BOT v2.0 - ESTRATEGIA SINCRONIZADA':^78}║")
        print(f"║{f'Uptime: {str(uptime).split('.')[0]} | UTC: {datetime.now(timezone.utc).strftime('%H:%M:%S')}':^78}║")
        print("╠" + "═" * 78 + "╣")
        
        # Stats Generales
        pnl_str = f"${self.pnl_today:,.2f}"
        print(f"║ Pares: {len(active_symbols):<10} | Posiciones: {len(self.positions)}/3 | PnL Hoy: {pnl_str:<23} ║")
        print("╠" + "═" * 78 + "╣")
        
        # Tabla de Mercado
        print(f"║ {'PAR':<12} {'FUNDING':<12} {'ESTADO / SEÑAL':<50} ║")
        print("╟" + "─" * 78 + "╢")
        
        for symbol, data in sorted(active_symbols.items()):
            rate_str = f"{data['funding']:+.4%}"
            signal = data['signal'][:48]
            icon = "🔍" if "MONITOREANDO" in signal else "🎯"
            print(f"║ {icon} {symbol:<9} {rate_str:<12} {signal:<50} ║")

        print("╠" + "═" * 78 + "╣")
        
        # SECCIÓN DE POSICIONES ACTIVAS (La gran mejora visual)
        if self.positions:
            print(f"║ {'POSICIONES EN CURSO (HOLD & FUNDING)':^78} ║")
            print(f"║ {'PAR':<10} {'L/S':<5} {'SIZE':<10} {'HOLD':<10} {'COBROS':<10} {'PRÓX. UTC':<15} ║")
            print("╟" + "─" * 78 + "╢")
            for symbol, pos in self.positions.items():
                side = pos['side'].upper()
                size = f"${pos['size_usd']:.0f}"
                hold = f"{pos['hold_hours']:.1f}h"
                cycles = f"x{pos['cycles_captured']}"
                next_f = pos['next_funding']
                
                # Icono dinámico según si ya capturó funding o no
                status_icon = "✅" if pos['cycles_captured'] > 0 else "⏳"
                
                print(f"║ {symbol:<10} {side:<5} {size:<10} {hold:<10} {status_icon} {cycles:<7} {next_f:<15} ║")
        else:
            print(f"║ {'--- SIN POSICIONES ABIERTAS (Esperando Break-even) ---':^78} ║")

        print("╠" + "═" * 78 + "╣")
        
       # --- SECCIÓN DE BALANCE ACTUALIZADA ---
        u_bal = self.balance.get('USDT', 0)
        c_bal = self.balance.get('USDC', 0)
        b_bal = self.balance.get('BTC', 0)
        
        # Formateamos con precisión: 2 decimales para stables, 4 para BTC
        balance_str = f"USDT: {u_bal:>8.2f} | USDC: {c_bal:>8.2f} | BTC: {b_bal:>8.4f}"
        print(f"║ BALANCE TOTAL: {balance_str:<60} ║")
        
        print("╠" + "═" * 78 + "╣")
        # Logs en pantalla
        for msg in self.messages[-3:]:
            print(f"║ {msg:<76} ║")
        print("╚" + "═" * 78 + "╝")
        print("\nPresiona Ctrl+C para detener el bot")

