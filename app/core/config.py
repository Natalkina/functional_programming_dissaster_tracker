from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    NASA_EONET_API: str = "https://eonet.gsfc.nasa.gov/api/v3/events"
    DISASTER_RADIUS_KM: float = 100.0

settings = Settings()