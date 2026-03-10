import asyncio
from app.services.functional_streams import process_disaster_stream
from app.core.config import settings

async def main():
    print("=" * 50)
    print("Приклад: Перевірка катастроф біля Києва")
    print("=" * 50)
    
    kyiv = (50.4501, 30.5234)
    
    events = await process_disaster_stream(
        settings.NASA_EONET_API,
        user_location=kyiv,
        radius_km=1000
    )
    
    print(f"\nЗнайдено {len(events)} катастроф в радіусі 1000км:")
    for e in events[:5]:
        print(f"  - {e.get('title')}")
        print(f"    Відстань: {e.get('distance_km')}км")
        print(f"    Рівень: {e.get('warning_level')}")
        print()

if __name__ == "__main__":
    asyncio.run(main())
