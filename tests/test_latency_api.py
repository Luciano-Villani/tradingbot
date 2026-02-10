import ccxt
import time
import statistics
import asyncio
from datetime import datetime

async def test_api_latency(exchange_id='binance', iterations=20, symbol='BTC/USDT'):
    print("="*60)
    print(f"TEST LATENCIA API - {exchange_id.upper()}")
    print(f"Inicio: {datetime.now().strftime('%H:%M:%S')}")
    print("="*60)
    
    try:
        exchange = getattr(ccxt, exchange_id)({
            'enableRateLimit': False,
            'options': {'defaultType': 'future'}
        })
        
        print("\n🔥 Calentando...")
        await exchange.fetch_ticker(symbol)
        await asyncio.sleep(1)
        
        print("\n📊 Test fetch_ticker...")
        latencies = []
        
        for i in range(iterations):
            start = time.perf_counter()
            try:
                ticker = await exchange.fetch_ticker(symbol)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)
                print(f"  {i+1:2d}: {elapsed:6.2f} ms | ${ticker['last']:,.2f}")
            except Exception as e:
                print(f"  {i+1:2d}: ERROR - {e}")
            await asyncio.sleep(0.2)
        
        if latencies:
            avg = statistics.mean(latencies)
            print(f"\n{'='*60}")
            print("RESULTADOS")
            print(f"Promedio: {avg:.2f} ms")
            print(f"Mínimo:   {min(latencies):.2f} ms")
            print(f"Máximo:   {max(latencies):.2f} ms")
            status = "✅ ÓPTIMO" if avg < 50 else "✅ BUENO" if avg < 100 else "⚠️  ACEPTABLE"
            print(f"Estado:   {status}")
        
        await exchange.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}")

def main():
    asyncio.run(test_api_latency())

if __name__ == "__main__":
    main()
    input("\nPresiona Enter...")

