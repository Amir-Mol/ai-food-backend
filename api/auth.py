from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, field_validator
import os
from datetime import datetime, timedelta, timezone
from google.oauth2 import id_token
from google.auth.transport import requests
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
import bcrypt
from prisma.errors import UniqueViolationError
from database import db # Import the shared db instance
from api.email_service import send_verification_email
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

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    newPassword: str

    # You can add the password validator here as well for consistency
    @field_validator('newPassword')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('password must be at least 8 characters long')
        if not re.search(r'[A-Z]', v):
            raise ValueError('password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('password must contain at least one number')
        return v


@router.post("/register", status_code=status.HTTP_200_OK)
async def register_user(user_data: UserCreate):
    existing_user = await db.user.find_unique(where={"email": user_data.email})
    if existing_user:
        # If user exists but is not verified, we can resend the code.
        # For now, we'll just treat it as a conflict to prevent re-registration attempts.
        if existing_user.isVerified:
            raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "error",
                "message": "This email address is already registered.",
                "errorCode": "EMAIL_EXISTS"
            },
        )
        # If user is not verified, we could allow this endpoint to trigger a new email.
        # However, a separate "resend" endpoint is cleaner. For now, we'll return a conflict.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered. Please verify your email or request a new code.")

    hashed_password = get_password_hash(user_data.password)
    verification_code = f"{random.randint(100000, 999999)}"
    hashed_code = get_password_hash(verification_code)
    # Set a 3-minute expiration time for the verification code
    expires = datetime.utcnow() + timedelta(minutes=3)

    try:
        # Assign user to a group
        group = random.choice(["control", "transparency"])
        await db.user.create(
            data={
                "email": user_data.email,
                "passwordHash": hashed_password,
                "group": group,
                "verificationToken": hashed_code,
                "verificationTokenExpires": expires,
            }
        )

        # ... inside the /register endpoint, after hashing the code ...
        print(f"DEBUG: Attempting to send verification email to {user_data.email}")
        try:
            await send_verification_email(user_data.email, verification_code)
            print("DEBUG: Email function call completed without error.")
        except Exception as e:
            print(f"!!!!!!!!!!!!!! DEBUG: ERROR SENDING EMAIL !!!!!!!!!!!!!!")
            print(e)
            print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            # Re-raise the exception so the user doesn'g get a false success
            raise HTTPException(status_code=500, detail="Failed to send email.")

        print("DEBUG: Returning 200 OK to user.")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Verification code sent. Please check your email."}
        )

    except UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "status": "error",
                "message": "This email address is already registered.",
                "errorCode": "EMAIL_EXISTS"
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": f"An unexpected error occurred: {e}", "errorCode": "SERVER_ERROR"},
        )

@router.post("/verify-email", status_code=status.HTTP_200_OK)
async def verify_email(request: VerifyEmailRequest):
    user = await db.user.find_unique(where={"email": request.email})

    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if user.isVerified:
        return JSONResponse(status_code=status.HTTP_200_OK, content={"message": "Email is already verified."})

    if not user.verificationToken or not user.verificationTokenExpires:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending verification for this user.")

    # Ensure the expiration time is timezone-aware for comparison
    if user.verificationTokenExpires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code has expired.")

    if not verify_password(request.code, user.verificationToken):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code.")

    # If code is correct, update the user
    await db.user.update(
        where={"id": user.id},
        data={
            "isVerified": True,
            "verificationToken": None,
            "verificationTokenExpires": None,
        }
    )

    return {"message": "Email verified successfully. You can now log in."}

@router.post("/resend-verification", status_code=status.HTTP_200_OK)
async def resend_verification(request: ForgotPasswordRequest):
    """
    Resends a verification code to a user's email.
    This is for users who did not receive the initial code or whose code expired.
    """
    user = await db.user.find_unique(where={"email": request.email})

    # Only proceed if the user exists and is not yet verified.
    # Otherwise, we do nothing but still return a success message to prevent email enumeration.
    if user and not user.isVerified:
        # Generate a new 6-digit random code and a 3-minute expiration time.
        verification_code = f"{random.randint(100000, 999999)}"
        hashed_code = get_password_hash(verification_code)
        expires = datetime.utcnow() + timedelta(minutes=3)

        # Save the new hashed code and expiration time
        await db.user.update(
            where={"id": user.id},
            data={
                "verificationToken": hashed_code,
                "verificationTokenExpires": expires,
            }
        )

        try:
            # Send the new plain text code to the user's email
            await send_verification_email(request.email, verification_code)
        except Exception as e:
            # Log the error but do not expose it to the client.
            print(f"ERROR: Failed to resend verification email to {request.email}. Error: {e}")

    return {"message": "A new verification code has been sent."}

@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(request: ForgotPasswordRequest):
    """
    Handles the first step of password reset. Generates a verification code
    and sends it to the user's email if the user exists.
    """
    user = await db.user.find_unique(where={"email": request.email})

    if user:
        # Generate a new 6-digit random code and a 15-minute expiration time.
        verification_code = f"{random.randint(100000, 999999)}"
        hashed_code = get_password_hash(verification_code)
        expires = datetime.utcnow() + timedelta(minutes=15)

        # Save the hashed code and expiration time
        await db.user.update(
            where={"id": user.id},
            data={
                "verificationToken": hashed_code,
                "verificationTokenExpires": expires,
            }
        )

        try:
            # Send the plain text code to the user's email
            await send_verification_email(request.email, verification_code)
        except Exception as e:
            # Log the error but do not expose it to the client to prevent information leakage.
            print(f"ERROR: Failed to send password reset email to {request.email}. Error: {e}")

    return {"message": "If this email is registered, a password reset code has been sent."}

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(request: ResetPasswordRequest):
    """
    Resets the user's password after they have verified their reset code.
    """
    user = await db.user.find_unique(where={"email": request.email})

    # Use a generic error message to prevent user enumeration
    invalid_code_exception = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired code."
    )

    if not user or not user.verificationToken or not user.verificationTokenExpires:
        raise invalid_code_exception

    # Check if the code has expired
    if user.verificationTokenExpires.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise invalid_code_exception

    # Check if the code is correct
    if not verify_password(request.code, user.verificationToken):
        raise invalid_code_exception

    # If the code is valid, hash the new password
    new_hashed_password = get_password_hash(request.newPassword)

    # Update the user's password and clear the verification token fields
    await db.user.update(
        where={"id": user.id},
        data={
            "passwordHash": new_hashed_password,
            "verificationToken": None,
            "verificationTokenExpires": None,
        }
    )

    return {"message": "Password reset successful."}

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
                "isVerified": True, # Google-verified emails are considered trusted
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
    
    if not user.isVerified:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Please verify your email before logging in.")

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
