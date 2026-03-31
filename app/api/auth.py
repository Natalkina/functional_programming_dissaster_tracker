import logging
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.fp_core import Ok, Err, Result
from app.core.domain import RegisterResponse, LoginResponse
from app.models import User
from app.core.security import hash_password, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class UserCreate(BaseModel):
    email: str
    password: str


def ensure_email_available(db: Session, email: str) -> Result:
    """
    find_user_by_email returns Ok when the email exists, but for registration
    "email exists" is a failure. this function flips the semantics so that
    Err means "taken" and Ok means "available," keeping the Result orientation
    consistent throughout the chain: Ok always means "continue," Err always means "stop"
    """
    match find_user_by_email(db, email):
        case Ok():
            return Err("user already exists")
        case Err():
            return Ok(email)

# compare plain password against stored hash, no db access needed
def authenticate(user, plain_password: str) -> Result:
    match verify_password(plain_password, user.password):
        case True:
            return Ok(user)
        case False:
            return Err("invalid credentials")


# build typed response after successful registration
def make_register_response(user) -> RegisterResponse:
    return RegisterResponse(message="registered", user_id=user.id)


# build typed response after successful login
def make_login_response(user) -> LoginResponse:
    return LoginResponse(message="logged in", email=user.email, user_id=user.id)


# query db for a user row, returns Err when email is not in the table
def find_user_by_email(db: Session, email: str) -> Result:
    user = db.query(User).filter(User.email == email).first()
    match user:
        case None:
            return Err("user not found")
        case _:
            return Ok(user)

def create_user(db: Session, email: str, hashed_pw: str) -> Result:
    """
    IMPURE: insert a new user row, rolls back and returns Err on db failure
    """
    try:
        new_user = User(email=email, password=hashed_pw)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return Ok(new_user)
    except Exception as exc:
        db.rollback()
        return Err(str(exc))


# imperative shell, wires IO and core together

# the whole registration pipeline lives in one Result chain.
# ensure_email_available returns Ok(email) if we can proceed,
# then map applies hash_password (pure, can't fail, so map not flat_map),
# then flat_map passes the hash to create_user which hits the db
# and can fail, so it returns Result and needs flat_map to avoid nesting.
# if any step returns Err, everything downstream is short-circuited.
@router.post("/register")
def register(body: UserCreate, db: Session = Depends(get_db)):

    result = (
        ensure_email_available(db, body.email)
        .map(lambda _: hash_password(body.password))
        .flat_map(lambda hashed: create_user(db, body.email, hashed))
    )

    # this is the boundary, the single point where we leave the Result
    # context and translate into the framework's language (HTTP responses).
    # the functional core above is pure composition; this match is the
    # imperative shell that converts Result into external effects.
    match result:
        case Ok(value=user):
            return make_register_response(user)
        case Err(error=err):
            return JSONResponse(status_code=400, content={"detail": err})

@router.post("/login")
def login(body: UserCreate, db: Session = Depends(get_db)):
    # flat_map chains db lookup into credential check, Err short-circuits
    result = find_user_by_email(db, body.email).flat_map(
        lambda user: authenticate(user, body.password)
    )
    match result:
        case Ok(value=user):
            return make_login_response(user)
        case Err(error=err):
            return JSONResponse(status_code=401, content={"detail": err})
