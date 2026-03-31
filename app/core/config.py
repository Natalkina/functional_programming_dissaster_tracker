from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    DATABASE_URL: str = "postgresql://disaster_user:disaster_pass@localhost:5432/disaster_tracker"
    NASA_EONET_API: str = "https://eonet.gsfc.nasa.gov/api/v3/events"
    DISASTER_RADIUS_KM: float = 100.0

    # ── Google OAuth2 / Calendar ──────────────────────────
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/calendar/google/oauth/callback"
    OAUTH_STATE_SECRET: str = "change-me-to-a-random-secret"
    GOOGLE_SCOPES: str = "openid email https://www.googleapis.com/auth/calendar.readonly"
    CALENDAR_POLL_INTERVAL: int = 30

settings = Settings()