from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, field_validator
import os
from datetime import datetime, timedelta
from google.oauth2 import id_token
from google.auth.transport import requests
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
import bcrypt
from prisma.errors import UniqueViolationError
from database import db # Import the shared db instance
import re
import random
from prisma.models import User
from typing import Annotated # Import Annotated for type hinting dependencies
from jose import JWTError, jwt

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")

if not SECRET_KEY or not ALGORITHM:
    raise ValueError("SECRET_KEY and ALGORITHM must be set in environment variables")

if not GOOGLE_CLIENT_ID:
    raise ValueError("GOOGLE_CLIENT_ID must be set in environment variables")

# OAuth2 scheme for token authentication
# This tells FastAPI how to expect the token (Bearer token in Authorization header)
# and where to find the login endpoint for OpenAPI documentation.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

async def get_current_active_user(token: Annotated[str, Depends(oauth2_scheme)]) -> User:
    """
    Decodes the JWT token, validates it, and retrieves the corresponding active user from the database.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await db.user.find_unique(where={"id": user_id})
    if user is None:
        raise credentials_exception
    return user

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# Password hashing context

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# Pydantic model for user registration request (now UserCreate)
class UserCreate(BaseModel):
    email: EmailStr
    password: str

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        # Ensure password is at least 8 characters long
        if len(v) < 8:
            raise ValueError('password must be at least 8 characters long')
        # Ensure password contains at least one uppercase letter
        if not re.search(r'[A-Z]', v):
            raise ValueError('password must contain at least one uppercase letter')
        # Ensure password contains at least one lowercase letter
        if not re.search(r'[a-z]', v):
            raise ValueError('password must contain at least one lowercase letter')
        # Ensure password contains at least one number
        if not re.search(r'[0-9]', v):
            raise ValueError('password must contain at least one number')
        return v

class GoogleToken(BaseModel):
    token: str

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate):
    # Remove response_model=UserRead from the decorator, as we are returning a JSONResponse directly.
    # The status_code remains HTTP_201_CREATED.
    # Check if a user with this email already exists
    existing_user = await db.user.find_unique(where={"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "error",
                "message": "This email address is already registered.",
                "errorCode": "EMAIL_EXISTS"
            },
        )

    hashed_password = get_password_hash(user_data.password)

    try:
        # Assign user to a group
        group = random.choice(["control", "transparency"])
        new_user = await db.user.create(
            data={
                "email": user_data.email,
                "passwordHash": hashed_password,
                "group": group,
            }
        )
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "status": "success",
                "message": "User registered successfully.",
                "data": {"userId": new_user.id, "email": new_user.email},
            },
        )
    except UniqueViolationError:
        # This block handles potential race conditions where two requests try to register
        # the same email simultaneously and both pass the initial check.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "error",
                "message": "This email address is already registered.",
                "errorCode": "EMAIL_EXISTS"
            },
        )
    except Exception as e:
        # Catch any other unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": f"An unexpected error occurred: {e}", "errorCode": "SERVER_ERROR"},
        )

@router.post("/google-login")
async def google_login(google_token: GoogleToken):
    try:
        idinfo = id_token.verify_oauth2_token(
            google_token.token, requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError:
        # Invalid token
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    user_email = idinfo.get("email")
    user_name = idinfo.get("name")

    if not user_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not found in Google token",
        )

    user = await db.user.find_unique(where={"email": user_email})

    if not user:
        # User does not exist, create a new one
        group = random.choice(["control", "transparency"])
        user = await db.user.create(
            data={
                "email": user_email,
                "name": user_name,
                "group": group,
                # passwordHash can be null for Google-signed-in users
            }
        )

    # User exists or was just created, generate token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "onboardingCompleted": user.onboardingCompleted,
        "email": user.email,
        "name": user.name,
    }

@router.post("/login", response_model=None)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    # Find the user in the database by email
    user = await db.user.find_unique(where={"email": form_data.username})

    # If no user is found or password does not match, raise HTTPException
    if not user or not verify_password(form_data.password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"}, # Standard header for OAuth2
        )

    # Create a JWT access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "onboardingCompleted": user.onboardingCompleted,
        "email": user.email,
        "name": user.name,
    }

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout_user(current_user: Annotated[User, Depends(get_current_active_user)]):
    """
    Logs out the current user.

    In a stateless JWT setup, this endpoint's main purpose is to provide a secure
    endpoint for the client to call upon logout. The client is responsible for
    deleting the token. If using a token blocklist, the token invalidation
    logic would go here.
    """
    # The dependency `get_current_active_user` handles token validation.
    return {"status": "success", "message": "User logged out successfully."}
