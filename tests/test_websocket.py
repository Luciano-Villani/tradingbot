import asyncio
import websockets
import json
import time
import statistics
from datetime import datetime

async def test_binance_websocket(duration_seconds=30):
    print("="*60)
    print("TEST WEBSOCKET - Binance Futures")
    print(f"Duración: {duration_seconds} segundos")
    print("="*60)
    
    uri = "wss://fstream.binance.com/ws/btcusdt@bookTicker"
    latencies = []
    messages = 0
    start_time = time.time()
    
    try:
        print(f"\n🔌 Conectando...")
        async with websockets.connect(uri) as ws:
            print("✅ Conectado.\n")
            
            while time.time() - start_time < duration_seconds:
                try:
                    msg_start = time.perf_counter()
                    message = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    elapsed = (time.perf_counter() - msg_start) * 1000
                    
                    data = json.loads(message)
                    if 'b' in data and 'a' in data:
                        latencies.append(elapsed)
                        messages += 1
                        
                        if messages % 10 == 0:
                            avg_lat = statistics.mean(latencies[-10:])
                            print(f"  Msgs: {messages:3d} | "
                                  f"Lat: {elapsed:5.2f}ms | "
                                  f"Avg(10): {avg_lat:5.2f}ms")
                    
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    print(f"  ⚠️ {e}")
                    continue
            
            await ws.close()
        
        if latencies:
            avg = statistics.mean(latencies)
            print(f"\n{'='*60}")
            print("RESULTADOS")
            print(f"Mensajes: {messages}")
            print(f"Promedio: {avg:.2f} ms")
            print(f"Mínimo:   {min(latencies):.2f} ms")
            print(f"Máximo:   {max(latencies):.2f} ms")
            status = "✅ EXCELENTE" if avg < 20 else "✅ MUY BUENO" if avg < 50 else "✅ BUENO"
            print(f"Estado:   {status}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_binance_websocket(30))
    input("\nPresiona Enter...")

