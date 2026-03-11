from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://disaster_user:disaster_pass@localhost:5432/disaster_tracker"
    NASA_EONET_API: str = "https://eonet.gsfc.nasa.gov/api/v3/events"
    DISASTER_RADIUS_KM: float = 100.0
    
    class Config:
        env_file = ".env"

settings = Settings()