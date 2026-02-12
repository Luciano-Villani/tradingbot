import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List

class Dashboard:
    """Dashboard en tiempo real para consola corregido"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.last_update = None
        self.symbols_data: Dict[str, Dict] = {}
        self.positions: Dict[str, Dict] = {}
        self.balance = {'USDT': 0, 'USDC': 0, 'BTC': 0}
        self.pnl_today = 0.0
        self.opportunities_count = 0
        self.messages: List[str] = []
        
    def update_symbol(self, symbol: str, funding_rate: float, signal: str = None):
        """Actualiza datos de un par"""
        self.symbols_data[symbol] = {
            'funding': funding_rate,
            'signal': signal or 'SIN SEÑAL',
            'last_update': datetime.now()
        }
        self.last_update = datetime.now()

    def update_positions(self, positions: Dict):
        self.positions = positions

    def update_balance(self, balance: Dict):
        # Aseguramos que siempre sea un float para evitar errores visuales
        if isinstance(balance, (float, int)):
            self.balance = {'USDT': float(balance), 'USDC': 0.0, 'BTC': 0.0}
        else:
            self.balance = balance

    def update_pnl(self, pnl: float):
        self.pnl_today = pnl

    def increment_opportunities(self):
        self.opportunities_count += 1

    def add_message(self, msg: str):
        self.messages.append(f"{datetime.now().strftime('%H:%M:%S')} {msg}")
        if len(self.messages) > 5:
            self.messages.pop(0)

    def render(self):
        """Renderiza el dashboard filtrando únicamente los datos activos"""
        os.system('cls' if os.name == 'nt' else 'clear')
        uptime = datetime.now() - self.start_time
        
        # --- FILTRO CRÍTICO ---
        # Solo mostramos los símbolos que se actualizaron en los últimos 2 minutos
        # Esto elimina los pares "fantasma" que quedaron en memoria
        active_symbols = {
            s: d for s, d in self.symbols_data.items() 
            if d['last_update'] > datetime.now() - timedelta(minutes=2)
        }

        # Header
        print("╔" + "═" * 70 + "╗")
        print(f"║{'ARGENFUNDING BOT v1.2':^70}║")
        print(f"║{f'Uptime: {str(uptime).split('.')[0]}':^70}║")
        print("╠" + "═" * 70 + "╣")
        
        # Stats generales (Sincronizado con los 8 pares reales)
        print(f"║ Pares monitoreados: {len(active_symbols):<48} ║")
        print(f"║ Posiciones abiertas: {len(self.positions)}/3{'':<45} ║")
        print(f"║ Oportunidades hoy: {self.opportunities_count:<49} ║")
        print("╠" + "═" * 70 + "╣")
        
        # Tabla de pares
        print(f"║ {'PAR':<12} {'FUNDING':<12} {'SEÑAL':<42} ║")
        print("╠" + "═" * 70 + "╣")
        
        # Mostrar los pares activos
        displayed = 0
        for symbol, data in sorted(active_symbols.items()):
            if displayed >= 8: break
            
            funding = data['funding']
            signal = data['signal']
            funding_str = f"{funding:+.4%}"
            signal_display = (signal[:40] + '..') if len(signal) > 40 else signal
            
            icon = "  "
            if "EJECUTANDO" in signal or "🎯" in signal: icon = "🎯"
            elif "MONITOREANDO" in signal: icon = "🔍"
            
            print(f"║ {icon} {symbol:<10} {funding_str:<12} {signal_display:<42} ║")
            displayed += 1
        
        # Rellenar huecos si faltan datos
        for _ in range(max(0, 8 - displayed)):
            print(f"║ {'':<12} {'':<12} {'':<42} ║")
        
        print("╠" + "═" * 70 + "╣")
        
        # Balance y PnL
        usdt = self.balance.get('USDT', 0)
        pnl_str = f"+${self.pnl_today:,.2f}" if self.pnl_today >= 0 else f"-${abs(self.pnl_today):,.2f}"
        print(f"║ BALANCE USDT: ${usdt:>12,.2f} | PnL HOY: {pnl_str:>24} ║")
        print("╠" + "═" * 70 + "╣")
        
        # Posiciones
        if self.positions:
            print(f"║ {'POSICIONES ABIERTAS':^70} ║")
            for symbol, pos in list(self.positions.items())[:3]:
                side = str(pos.get('side', 'N/A')).upper()
                size = pos.get('size_usd', 0)
                print(f"║ {symbol:<10} | {side:<6} | ${size:>8,.2f} | Activa {'':<27} ║")
        else:
            print(f"║ {'Sin posiciones activas':^70} ║")
        
        print("╠" + "═" * 70 + "╣")
        
        # Log de mensajes
        for msg in self.messages[-3:]:
            print(f"║ {msg[:68]:<68} ║")
        
        print("╚" + "═" * 70 + "╝")
        print("Presiona Ctrl+C para detener el bot")
        