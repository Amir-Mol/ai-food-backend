from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from typing import Annotated, List, Optional
from datetime import datetime

from api.auth import get_current_active_user
from prisma.models import User
from database import db

class HistoryItem(BaseModel):
    """Defines the structure for a single item in the user's history."""
    recommendationName: str = Field(alias="foodName")
    createdAt: datetime = Field(alias="recommendedOn")
    liked: Optional[bool] = None
    healthinessScore: Optional[int] = None
    tastinessScore: Optional[int] = None
    intentToTryScore: Optional[int] = None

    class Config:
        populate_by_name = True

class PaginatedHistoryResponse(BaseModel):
    """The final paginated response for the history endpoint."""
    history: List[HistoryItem]
    total_items: int = Field(alias="totalItems") # Use an alias for the total count
    page: int
    page_size: int = Field(alias="pageSize")

    class Config:
        populate_by_name = True

router = APIRouter(
    prefix="/user/history",
    tags=["History"],
)

@router.get("/", response_model=PaginatedHistoryResponse)
async def get_user_history(
    current_user: Annotated[User, Depends(get_current_active_user)],
    page: int = 1,
    pageSize: int = 10,
):
    """
    Fetches the user's recommendation history from the TrainingRecord table.
    Supports pagination.
    """
    skip = (page - 1) * pageSize
    
    where_clause = {"userId": current_user.id, "liked": {"not": None}}

    # Query the TrainingRecord table for the user's records with pagination
    history_records = await db.trainingrecord.find_many(
        where=where_clause,
        order={"createdAt": "desc"},
        skip=skip,
        take=pageSize,
    )
    
    # Get the total count of records for the user for pagination metadata
    total_records = await db.trainingrecord.count(
        where=where_clause
    )


    # This ensures that the aliases ('foodName', 'recommendedOn') are used in the response.
    history_data = [HistoryItem(**record.dict()) for record in history_records]

    return PaginatedHistoryResponse(
        history=history_data, # Use the newly created list
        total_items=total_records,
        page=page,
        page_size=pageSize,
    )