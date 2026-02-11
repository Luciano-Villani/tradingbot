import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List

class Dashboard:
    """Dashboard en tiempo real para consola"""
    
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
        """Actualiza posiciones abiertas"""
        self.positions = positions
    
    def update_balance(self, balance: Dict):
        """Actualiza balance"""
        self.balance = balance
    
    def update_pnl(self, pnl: float):
        """Actualiza PnL"""
        self.pnl_today = pnl
    
    def increment_opportunities(self):
        self.opportunities_count += 1
    
    def add_message(self, msg: str):
        """Agrega mensaje al log"""
        self.messages.append(f"{datetime.now().strftime('%H:%M:%S')} {msg}")
        if len(self.messages) > 5:
            self.messages.pop(0)
    
    def render(self):
        """Renderiza el dashboard en consola"""
        os.system('cls' if os.name == 'nt' else 'clear')
        
        uptime = datetime.now() - self.start_time
        
        # Header
        print("╔" + "═" * 70 + "╗")
        print(f"║{'ARGENFUNDING BOT v1.2':^70}║")
        print(f"║{f'Uptime: {str(uptime).split('.')[0]}':^70}║")
        print("╠" + "═" * 70 + "╣")
        
        # Stats generales
        print(f"║ Pares monitoreados: {len(self.symbols_data):<48} ║")
        print(f"║ Posiciones abiertas: {len(self.positions)}/3{'':<45} ║")
        print(f"║ Oportunidades hoy: {self.opportunities_count:<49} ║")
        print("╠" + "═" * 70 + "╣")
        
        # Tabla de pares
        print(f"║ {'PAR':<12} {'FUNDING':<12} {'SEÑAL':<42} ║")
        print("╠" + "═" * 70 + "╣")
        
        # Mostrar hasta 8 pares
        displayed = 0
        for symbol, data in sorted(self.symbols_data.items()):
            if displayed >= 8:
                break
            funding = data['funding']
            signal = data['signal']
            funding_str = f"{funding:+.4%}"
            signal_display = signal[:40] if len(signal) > 40 else signal
            
            icon = "  "
            if "SHORT" in signal or "LONG" in signal:
                icon = "🎯"
            elif "CERRADA" in signal:
                icon = "📭"
            elif "ABIERTA" in signal:
                icon = "📈"
            
            print(f"║ {icon} {symbol:<10} {funding_str:<12} {signal_display:<42} ║")
            displayed += 1
        
        # Rellenar si hay menos de 8
        for _ in range(max(0, 8 - displayed)):
            print(f"║ {'':<12} {'':<12} {'':<42} ║")
        
        print("╠" + "═" * 70 + "╣")
        
        # Balance
        usdt = self.balance.get('USDT', 0)
        usdc = self.balance.get('USDC', 0)
        btc = self.balance.get('BTC', 0)
        
        print(f"║ BALANCE  USDT: ${usdt:>12,.2f}  USDC: ${usdc:>12,.2f}{'':<12} ║")
        print(f"║          BTC:  {btc:>12.6f}{'':<48} ║")
        
        pnl_str = f"+${self.pnl_today:,.2f}" if self.pnl_today >= 0 else f"-${abs(self.pnl_today):,.2f}"
        print(f"║ PnL HOY: {pnl_str:>56} ║")
        print("╠" + "═" * 70 + "╣")
        
        # Posiciones abiertas
        if self.positions:
            print(f"║ {'POSICIONES ABIERTAS':^70} ║")
            for symbol, pos in list(self.positions.items())[:3]:
                side = pos.get('side', 'N/A').upper()
                size = pos.get('size_usd', 0)
                entry = pos.get('entry_rate', 0)
                print(f"║ {symbol} | {side} | ${size:,.2f} | Entry: {entry:.4%}{'':<20} ║")
        else:
            print(f"║ {'Sin posiciones abiertas':^70} ║")
        
        print("╠" + "═" * 70 + "╣")
        
        # Mensajes recientes
        print(f"║ {'MENSAJES RECIENTES':^70} ║")
        for msg in self.messages[-3:]:
            truncated = msg[:66] if len(msg) > 66 else msg
            print(f"║ {truncated:<70} ║")
        
        if not self.messages:
            print(f"║ {'Esperando actividad...':^70} ║")
        
        print("╚" + "═" * 70 + "╝")
        print("\nPresiona Ctrl+C para detener el bot")
        