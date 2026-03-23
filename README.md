# 🌍 Disaster Tracker

Перед тим як їхати в Дубаї, переконайся що все добре!

## Запуск

### З Docker Compose (рекомендовано)

```bash
docker-compose up --build
```

### Локально

```bash
# Встановити залежності
pip install -r requirements.txt

# Створити .env файл
cp .env.example .env

# Запустити PostgreSQL (або використати Docker)
docker run -d -p 5432:5432 \
  -e POSTGRES_USER=disaster_user \
  -e POSTGRES_PASSWORD=disaster_pass \
  -e POSTGRES_DB=disaster_tracker \
  postgres:15-alpine

# Запустити додаток
python3 -m uvicorn app.main:app --reload
```

Відкрити: `http://localhost:8000`

## Функціонал

✅ **NASA EONET API** - інтеграція з центром сповіщень про катастрофи  
✅ **Real-time API** - отримання подій в реальному часі  
✅ **Google Calendar** - відстеження подій користувача  
✅ **Сповіщення** - попередження про небезпеку біля запланованих подій  
✅ **Hotspots** - найнебезпечніші місця світу  
✅ **Аутентифікація** - реєстрація та логін користувачів  
✅ **Функціональне програмування** - aiostream, pure functions, reduce

## API Endpoints

### Disasters
```bash
# Всі катастрофи
GET /disasters/events

# По даті
GET /disasters/events/by-date?start_date=2026-04-01&end_date=2026-05-01

# По локації
GET /disasters/events/by-location?lat=50.45&lon=30.52&radius_km=500

# Гарячі точки
GET /disasters/hotspots?limit=10
```

### Calendar
```bash
# Додати подію
POST /calendar/events
{
  "title": "Подорож до Києва",
  "location": "Kyiv, Ukraine",
  "date": "2026-06-15"
}

# Отримати події
GET /calendar/events
GET /calendar/events?date=2024-06-15

# Перевірити катастрофи
GET /calendar/check-disasters?start_date=2024-06-01&end_date=2024-06-30

# Відправити сповіщення
POST /calendar/notify-warnings?start_date=2024-06-01&end_date=2024-06-30

# Перевірити чи безпечна локація
GET /calendar/hotspot-warnings?location=Dubai
```

### Auth
```bash
# Реєстрація
POST /auth/register
{
  "email": "user@example.com",
  "password": "password123"
}

# Логін
POST /auth/login
{
  "email": "user@example.com",
  "password": "password123"
}
```

## Архітектура

![Architecture](app/static/schema.png)


## Приклад використання

```bash
# Запустити сервер
python3 -m uvicorn app.main:app --reload

# Додати подію
curl -X POST http://localhost:8000/calendar/events \
  -H "Content-Type: application/json" \
  -d '{"title":"Trip to Dubai","location":"Dubai","date":"2024-07-01"}'

# Перевірити небезпеку
curl "http://localhost:8000/calendar/check-disasters?start_date=2024-07-01&end_date=2024-07-31"

# Перевірити чи безпечно
curl "http://localhost:8000/calendar/hotspot-warnings?location=Dubai"
```


## Рівні небезпеки

- 🔴 **HIGH**: < 50км - Дуже небезпечно!
- 🟡 **MEDIUM**: 50-100км - Обережно
- 🔵 **LOW**: > 100км - Моніторити

## Ліцензія

MIT
