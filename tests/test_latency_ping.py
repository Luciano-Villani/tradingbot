import subprocess
import platform
import statistics
from datetime import datetime

def test_ping_latency(hosts=None, count=10):
    if hosts is None:
        hosts = {
            'Binance API': 'api.binance.com',
            'Binance Futures': 'fapi.binance.com',
            'Bybit': 'api.bybit.com',
            'Google DNS': '8.8.8.8'
        }
    
    print("="*60)
    print("TEST LATENCIA ICMP")
    print(f"Inicio: {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)
    
    results = {}
    
    for name, host in hosts.items():
        print(f"\n📡 {name} ({host})")
        print("-" * 40)
        
        try:
            if platform.system().lower() == 'windows':
                cmd = ['ping', '-n', str(count), host]
            else:
                cmd = ['ping', '-c', str(count), host]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            output = result.stdout
            
            times = []
            for line in output.split('\n'):
                if 'tiempo=' in line or 'time=' in line:
                    try:
                        if 'tiempo=' in line:
                            time_part = line.split('tiempo=')[1].split('ms')[0]
                        else:
                            time_part = line.split('time=')[1].split('ms')[0]
                        times.append(float(time_part))
                    except:
                        continue
            
            if times:
                avg = statistics.mean(times)
                print(f"  Promedio: {avg:.2f} ms")
                print(f"  Mínimo:   {min(times):.2f} ms")
                print(f"  Máximo:   {max(times):.2f} ms")
                status = "✅ EXCELENTE" if avg < 10 else "✅ BUENO" if avg < 50 else "⚠️  ACEPTABLE"
                print(f"  Estado:   {status}")
                results[name] = {'avg': avg, 'min': min(times), 'max': max(times)}
            else:
                print("  ❌ No se pudieron parsear tiempos")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    print("\n" + "="*60)
    print("RESUMEN")
    print("="*60)
    for name, data in results.items():
        print(f"{name:20s}: {data['avg']:6.2f} ms")
    
    return results

if __name__ == "__main__":
    test_ping_latency()
    input("\nPresiona Enter...")
