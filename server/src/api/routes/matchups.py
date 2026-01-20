"""Matchup and synergy endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List
from ...db import Database
from ..dependencies import get_db
from ..models import (
    ChampionMatchupsResponse,
    MatchupResponse,
    BulkMatchupsResponse,
    ChampionSynergiesResponse,
    SynergyResponse,
    BulkSynergiesResponse,
)

router = APIRouter()


# ========== Matchup Endpoints ==========


@router.get("/champions/{champion_id}/matchups", response_model=ChampionMatchupsResponse)
def get_champion_matchups(champion_id: int, db: Database = Depends(get_db)):
    """
    Get all matchups for a specific champion.

    Args:
        champion_id: Champion database ID

    Returns:
        ChampionMatchupsResponse: Matchup data for all enemies
    """
    try:
        # Get champion name
        champion_name = db.get_champion_name(champion_id)
        if not champion_name:
            raise HTTPException(status_code=404, detail=f"Champion with ID {champion_id} not found")

        # Get matchups
        matchups_data = db.get_champion_matchups_by_name(champion_name)

        # Convert to Pydantic models
        matchups = [
            MatchupResponse(
                enemy_id=db.get_champion_id(m.enemy_name),
                enemy_name=m.enemy_name,
                winrate=m.winrate,
                games=m.games,
                delta2=m.delta2,
                pickrate=m.pickrate,
                delta1=m.delta1,
            )
            for m in matchups_data
        ]

        return ChampionMatchupsResponse(
            champion_id=champion_id,
            champion_name=champion_name,
            matchups=matchups,
            count=len(matchups),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch matchups: {str(e)}")


@router.get("/matchups/bulk", response_model=BulkMatchupsResponse)
def get_bulk_matchups(db: Database = Depends(get_db)):
    """
    Get all matchups for all champions (bulk endpoint for cache).

    Returns:
        BulkMatchupsResponse: Dict mapping champion_id to matchups list
    """
    try:
        all_champions = db.get_all_champions()
        bulk_matchups = {}

        for champ_id, champ_name in all_champions:
            matchups_data = db.get_champion_matchups_by_name(champ_name)

            matchups = [
                MatchupResponse(
                    enemy_id=db.get_champion_id(m.enemy_name),
                    enemy_name=m.enemy_name,
                    winrate=m.winrate,
                    games=m.games,
                    delta2=m.delta2,
                    pickrate=m.pickrate,
                    delta1=m.delta1,
                )
                for m in matchups_data
            ]

            bulk_matchups[str(champ_id)] = matchups

        return BulkMatchupsResponse(matchups=bulk_matchups, count=len(bulk_matchups))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch bulk matchups: {str(e)}")


# ========== Synergy Endpoints ==========


@router.get("/champions/{champion_id}/synergies", response_model=ChampionSynergiesResponse)
def get_champion_synergies(champion_id: int, db: Database = Depends(get_db)):
    """
    Get all synergies for a specific champion.

    Args:
        champion_id: Champion database ID

    Returns:
        ChampionSynergiesResponse: Synergy data for all allies
    """
    try:
        # Get champion name
        champion_name = db.get_champion_name(champion_id)
        if not champion_name:
            raise HTTPException(status_code=404, detail=f"Champion with ID {champion_id} not found")

        # Get synergies
        synergies_data = db.get_champion_synergies_by_name(champion_name, as_dataclass=True)

        # Convert to Pydantic models
        synergies = [
            SynergyResponse(
                ally_id=db.get_champion_id(s.ally_name),
                ally_name=s.ally_name,
                winrate=s.winrate,
                games=s.games,
                delta2=s.delta2,
                pickrate=s.pickrate,
            )
            for s in synergies_data
        ]

        return ChampionSynergiesResponse(
            champion_id=champion_id,
            champion_name=champion_name,
            synergies=synergies,
            count=len(synergies),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch synergies: {str(e)}")


@router.get("/synergies/bulk", response_model=BulkSynergiesResponse)
def get_bulk_synergies(db: Database = Depends(get_db)):
    """
    Get all synergies for all champions (bulk endpoint for cache).

    Returns:
        BulkSynergiesResponse: Dict mapping champion_id to synergies list
    """
    try:
        all_champions = db.get_all_champions()
        bulk_synergies = {}

        for champ_id, champ_name in all_champions:
            synergies_data = db.get_champion_synergies_by_name(champ_name, as_dataclass=True)

            synergies = [
                SynergyResponse(
                    ally_id=db.get_champion_id(s.ally_name),
                    ally_name=s.ally_name,
                    winrate=s.winrate,
                    games=s.games,
                    delta2=s.delta2,
                    pickrate=s.pickrate,
                )
                for s in synergies_data
            ]

            bulk_synergies[str(champ_id)] = synergies

        return BulkSynergiesResponse(synergies=bulk_synergies, count=len(bulk_synergies))

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch bulk synergies: {str(e)}")
