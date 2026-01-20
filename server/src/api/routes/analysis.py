"""Team analysis and ban recommendation endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List
from ...db import Database
from ...analysis.scoring import ChampionScorer
from ...analysis.team_analysis import TeamAnalyzer
from ...constants import SOLOQ_POOL
from ..dependencies import get_db
from ..models import (
    TeamAnalysisRequest,
    TeamAnalysisResponse,
    ChampionResponse,
    SynergyDetail,
    BanRecommendationsResponse,
    BanRecommendation,
)

router = APIRouter()


@router.post("/analyze-team", response_model=TeamAnalysisResponse)
def analyze_team(request: TeamAnalysisRequest, db: Database = Depends(get_db)):
    """
    Analyze team composition holistically.

    Args:
        request: TeamAnalysisRequest with champion_ids (1-5 champions)

    Returns:
        TeamAnalysisResponse: Team analysis with matchup and synergy scores
    """
    try:
        # Validate champion IDs
        champion_names = []
        for champ_id in request.champion_ids:
            champ_name = db.get_champion_name(champ_id)
            if not champ_name:
                raise HTTPException(
                    status_code=404, detail=f"Champion with ID {champ_id} not found"
                )
            champion_names.append(champ_name)

        # Calculate scores
        scorer = ChampionScorer(db, verbose=False)

        # Matchup score: Average advantage against blind pick
        matchup_scores = []
        for champ_name in champion_names:
            matchups = db.get_champion_matchups_by_name(champ_name)
            advantage = scorer.score_against_team(matchups, [], champion_name=champ_name)
            matchup_scores.append(50.0 + advantage)  # Convert to winrate

        matchup_score = sum(matchup_scores) / len(matchup_scores)

        # Synergy score: Average delta2 of all pairs
        synergy_details = []
        synergy_scores = []

        for i, champ1 in enumerate(champion_names):
            for champ2 in champion_names[i + 1 :]:
                # Get synergy between champ1 and champ2
                synergies = db.get_champion_synergies_by_name(champ1, as_dataclass=True)
                matching_synergy = next((s for s in synergies if s.ally_name == champ2), None)

                if matching_synergy:
                    synergy_details.append(
                        SynergyDetail(
                            pair=[champ1, champ2],
                            winrate=matching_synergy.winrate,
                            games=matching_synergy.games,
                        )
                    )
                    synergy_scores.append(matching_synergy.delta2)

        synergy_score = sum(synergy_scores) / len(synergy_scores) if synergy_scores else 0.0

        # Holistic score: Weighted combination
        holistic_score = matchup_score * 0.6 + (50.0 + synergy_score) * 0.4

        # Generate recommendations
        recommendations = []
        if matchup_score < 48:
            recommendations.append("Consider champions with higher blind pick winrates")
        if synergy_score < -1.0:
            recommendations.append("Team composition has below-average synergy")
        elif synergy_score > 2.0:
            recommendations.append("Strong synergy between champions")

        # Build response
        return TeamAnalysisResponse(
            champions=[
                ChampionResponse(id=db.get_champion_id(name), name=name, riot_id=name.lower())
                for name in champion_names
            ],
            matchup_score=matchup_score,
            synergy_score=synergy_score,
            holistic_score=holistic_score,
            synergy_details=synergy_details,
            recommendations=recommendations,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze team: {str(e)}")


@router.get("/ban-recommendations", response_model=BanRecommendationsResponse)
def get_ban_recommendations(
    pool: str = Query(..., description="Champion pool to protect (TOP, JUNGLE, MID, ADC, SUPPORT)"),
    db: Database = Depends(get_db),
):
    """
    Get ban recommendations for a champion pool.

    Args:
        pool: Champion pool name

    Returns:
        BanRecommendationsResponse: List of recommended bans
    """
    try:
        # Map pool names to champion lists
        POOL_MAP = {
            "TOP": [],  # Will be populated from constants
            "JUNGLE": [],
            "MID": [],
            "ADC": [],
            "SUPPORT": [],
        }
        from ...constants import TOP_LIST, JUNGLE_LIST, MID_LIST, ADC_LIST, SUPPORT_LIST

        POOL_MAP = {
            "TOP": TOP_LIST,
            "JUNGLE": JUNGLE_LIST,
            "MID": MID_LIST,
            "ADC": ADC_LIST,
            "SUPPORT": SUPPORT_LIST,
        }

        # Validate pool
        pool_upper = pool.upper()
        if pool_upper not in POOL_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pool '{pool}'. Must be one of: {', '.join(POOL_MAP.keys())}",
            )

        champion_pool = POOL_MAP[pool_upper]

        # Calculate ban scores: Find champions that counter our pool the most
        scorer = ChampionScorer(db, verbose=False)
        ban_scores = {}

        # For each potential enemy champion, calculate average advantage vs our pool
        all_champions = db.get_all_champions()
        for enemy_id, enemy_name in all_champions:
            if enemy_name in champion_pool:
                continue  # Don't ban our own pool

            # Calculate how well this enemy does vs our pool
            advantages = []
            for our_champion in champion_pool:
                our_matchups = db.get_champion_matchups_by_name(our_champion)
                # Find matchup vs this enemy
                matchup = next((m for m in our_matchups if m.enemy_name == enemy_name), None)
                if matchup:
                    # Negative delta2 means enemy counters us
                    advantages.append(-matchup.delta2)

            if advantages:
                avg_advantage = sum(advantages) / len(advantages)
                ban_scores[enemy_name] = avg_advantage

        # Sort by ban score (highest = most threatening to our pool)
        sorted_bans = sorted(ban_scores.items(), key=lambda x: x[1], reverse=True)[:10]

        # Build recommendations
        recommendations = []
        for enemy_name, ban_score in sorted_bans:
            reason = f"Counters {len([a for a in advantages if a > 0])} champions in your pool"
            recommendations.append(
                BanRecommendation(
                    champion_id=db.get_champion_id(enemy_name),
                    champion_name=enemy_name,
                    ban_score=ban_score,
                    reason=reason,
                )
            )

        return BanRecommendationsResponse(
            pool=pool_upper, recommendations=recommendations, count=len(recommendations)
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate ban recommendations: {str(e)}"
        )
