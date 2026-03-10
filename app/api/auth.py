from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

users_db = {}

class User(BaseModel):
    email: str
    password: str

@router.post("/register")
async def register(user: User):
    if user.email in users_db:
        raise HTTPException(400, "User exists")
    users_db[user.email] = user.password
    return {"message": "Registered"}

@router.post("/login")
async def login(user: User):
    if users_db.get(user.email) != user.password:
        raise HTTPException(401, "Invalid credentials")
    return {"message": "Logged in", "email": user.email}