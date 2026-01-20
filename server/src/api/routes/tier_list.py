"""Tier list generation endpoint."""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from ...db import Database
from ...analysis.scoring import ChampionScorer
from ...analysis.tier_list import TierListGenerator
from ...constants import TOP_LIST, JUNGLE_LIST, MID_LIST, ADC_LIST, SUPPORT_LIST
from ..dependencies import get_db
from ..models import TierListResponse, ChampionTierEntry

router = APIRouter()

# Map pool names to champion lists
POOL_MAP = {
    "TOP": TOP_LIST,
    "JUNGLE": JUNGLE_LIST,
    "MID": MID_LIST,
    "ADC": ADC_LIST,
    "SUPPORT": SUPPORT_LIST,
}


@router.get("/tier-list", response_model=TierListResponse)
def get_tier_list(
    pool: str = Query(..., description="Champion pool (TOP, JUNGLE, MID, ADC, SUPPORT)"),
    type: str = Query(default="blind", description="Analysis type (blind or counter)"),
    db: Database = Depends(get_db),
):
    """
    Generate tier list for a champion pool.

    Args:
        pool: Champion pool name (TOP, JUNGLE, MID, ADC, SUPPORT)
        type: Analysis type ('blind_pick' or 'counter_pick')

    Returns:
        TierListResponse: Tier list with S/A/B/C rankings
    """
    try:
        # Validate pool
        pool_upper = pool.upper()
        if pool_upper not in POOL_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid pool '{pool}'. Must be one of: {', '.join(POOL_MAP.keys())}",
            )

        # Validate type
        analysis_type = "blind_pick" if type.lower() == "blind" else "counter_pick"
        if type.lower() not in ["blind", "counter"]:
            raise HTTPException(
                status_code=400, detail=f"Invalid type '{type}'. Must be 'blind' or 'counter'"
            )

        # Get champion pool
        champion_pool = POOL_MAP[pool_upper]

        # Generate tier list
        scorer = ChampionScorer(db, verbose=False)
        generator = TierListGenerator(db, scorer)
        tier_list_data = generator.generate_tier_list(champion_pool, analysis_type, verbose=False)

        # Convert to API response format
        tier_list_entries = [
            ChampionTierEntry(
                id=db.get_champion_id(item["champion"]),
                name=item["champion"],
                score=item["score"],
                tier=item["tier"],
            )
            for item in tier_list_data
        ]

        return TierListResponse(
            pool=pool_upper,
            type=type.lower(),
            tier_list=tier_list_entries,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate tier list: {str(e)}")
