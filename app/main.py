from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api import auth, disasters, calendar
from app.core.database import engine
from app.models import Base
import os

# Створити таблиці
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Disaster Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_path = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

app.include_router(auth.router)
app.include_router(disasters.router)
app.include_router(calendar.router)


# im just too lazy to rewrite this into functional style
@app.get("/")
async def root():
    index_path = os.path.join(static_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Disaster Tracker API", "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
