import os
from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel
from typing import Annotated, Optional
from dotenv import load_dotenv

from database import db

# Load environment variables from .env file
load_dotenv()
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY")


class SetGroupRequest(BaseModel):
    userId: str
    newGroup: str


async def verify_secret_key(x_admin_secret: Annotated[Optional[str], Header()] = None):
    if not ADMIN_SECRET_KEY:
        # This prevents the endpoint from being accessible if the key is not set on the server.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Admin secret key not configured on server.")
    if not x_admin_secret or x_admin_secret != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or missing admin secret key.")



router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(verify_secret_key)] # Applies secret key auth to all routes in this router
)

@router.post("/set-group", status_code=status.HTTP_200_OK)
async def set_user_group(request: SetGroupRequest):
    """
    Sets the experimental group for a given user.
    """
    if request.newGroup not in ["control", "transparency"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid group. Must be 'control' or 'transparency'.")

    updated_user = await db.user.update(
        where={"id": request.userId},
        data={"group": request.newGroup}
    )
    if not updated_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {request.userId} not found.")

    return {"status": "success", "message": f"User {updated_user.id} moved to group '{updated_user.group}'."}