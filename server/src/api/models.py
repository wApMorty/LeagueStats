"""Pydantic models for API request/response validation."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ========== Champion Models ==========


class ChampionResponse(BaseModel):
    """Response model for a single champion."""

    id: int
    name: str
    riot_id: Optional[str] = None


class ChampionsListResponse(BaseModel):
    """Response model for list of all champions."""
    champions: List[ChampionResponse]
    count: int


# ========== Matchup Models ==========

class MatchupResponse(BaseModel):
    """Response model for a single matchup."""
    enemy_id: int
    enemy_name: str
    winrate: float
    games: int
    delta2: float
    pickrate: Optional[float] = None
    delta1: Optional[float] = None


class ChampionMatchupsResponse(BaseModel):
    """Response model for champion matchups."""
    champion_id: int
    champion_name: str
    matchups: List[MatchupResponse]
    count: int


class BulkMatchupsResponse(BaseModel):
    """Response model for bulk matchups (all champions)."""
    matchups: Dict[str, List[MatchupResponse]]  # {champion_id: [matchups]}
    count: int


# ========== Synergy Models ==========

class SynergyResponse(BaseModel):
    """Response model for a single synergy."""
    ally_id: int
    ally_name: str
    winrate: float
    games: int
    delta2: float
    pickrate: Optional[float] = None


class ChampionSynergiesResponse(BaseModel):
    """Response model for champion synergies."""
    champion_id: int
    champion_name: str
    synergies: List[SynergyResponse]
    count: int


class BulkSynergiesResponse(BaseModel):
    """Response model for bulk synergies (all champions)."""
    synergies: Dict[str, List[SynergyResponse]]  # {champion_id: [synergies]}
    count: int


# ========== Tier List Models ==========

class TierListRequest(BaseModel):
    """Request model for tier list generation."""
    pool: str = Field(..., description="Champion pool name (e.g., 'TOP', 'JUNGLE')")
    type: str = Field(default="blind", description="Analysis type: 'blind' or 'counter'")


class ChampionTierEntry(BaseModel):
    """Individual champion entry in tier list."""
    id: int
    name: str
    score: float
    tier: str


class TierListResponse(BaseModel):
    """Response model for tier list."""
    pool: str
    type: str
    tier_list: List[ChampionTierEntry]
    generated_at: Optional[str] = None


# ========== Team Analysis Models ==========

class TeamAnalysisRequest(BaseModel):
    """Request model for team composition analysis."""
    champion_ids: List[int] = Field(..., min_length=1, max_length=5)


class SynergyDetail(BaseModel):
    """Synergy detail for a pair of champions."""
    pair: List[str]
    winrate: float
    games: int


class TeamAnalysisResponse(BaseModel):
    """Response model for team analysis."""
    champions: List[ChampionResponse]
    matchup_score: float
    synergy_score: float
    holistic_score: float
    synergy_details: List[SynergyDetail]
    recommendations: List[str]


# ========== Ban Recommendation Models ==========

class BanRecommendation(BaseModel):
    """Single ban recommendation."""
    champion_id: int
    champion_name: str
    ban_score: float
    reason: str


class BanRecommendationsResponse(BaseModel):
    """Response model for ban recommendations."""
    pool: str
    recommendations: List[BanRecommendation]
    count: int


# ========== Health Check Model ==========

class HealthCheckResponse(BaseModel):
    """Response model for health check endpoint."""
    status: str
    version: str
    database: str
    timestamp: Optional[str] = None
