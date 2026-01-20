"""Champion endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from typing import List
from ...db import Database
from ..dependencies import get_db
from ..models import ChampionsListResponse, ChampionResponse

router = APIRouter()


@router.get("/champions", response_model=ChampionsListResponse)
def get_all_champions(db: Database = Depends(get_db)):
    """
    Get list of all champions.

    Returns:
        ChampionsListResponse: List of all 172 champions with IDs
    """
    try:
        # Query all champions from database
        champions_data = db.get_all_champions()

        # Convert to Pydantic models
        champions = [
            ChampionResponse(
                id=champ_id,
                name=champ_name,
                riot_id=champ_name.lower()  # Simple riot_id mapping
            )
            for champ_id, champ_name in champions_data
        ]

        return ChampionsListResponse(
            champions=champions,
            count=len(champions)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch champions: {str(e)}")


@router.get("/champions/{champion_id}", response_model=ChampionResponse)
def get_champion_by_id(champion_id: int, db: Database = Depends(get_db)):
    """
    Get champion by ID.

    Args:
        champion_id: Champion database ID

    Returns:
        ChampionResponse: Champion data
    """
    try:
        champion_name = db.get_champion_name(champion_id)

        if not champion_name:
            raise HTTPException(status_code=404, detail=f"Champion with ID {champion_id} not found")

        return ChampionResponse(
            id=champion_id,
            name=champion_name,
            riot_id=champion_name.lower()
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch champion: {str(e)}")
