# TODO - League Stats Coach

## Feature Ideas & Improvements

### 🔍 Pool Statistics Viewer
**Priority**: Medium
**Status**: Not started
**Requested**: 2025-10-15

Add a "View Pool Statistics" option in the Pool Manager to display detailed champion statistics within a pool.

**Proposed features:**
- Display avg_delta2, variance, and coverage for each champion in a pool
- Show distribution metrics (min/max/mean/median) across the pool
- Identify outliers and champions with insufficient data
- Help diagnose tier list scoring anomalies
- Assist in adjusting normalization ranges based on observed data

**Integration point:**
```
Pool Manager Menu:
1. Create New Pool
2. Edit Existing Pool
3. Delete Pool
4. View Pool Statistics  ← NEW
5. Search Pools
6. Back
```

**Benefits:**
- Understand pool characteristics before generating tier lists
- Validate normalization ranges are appropriate for the role/pool
- Debug unexpected tier list scores
- Better insight into champion data quality

**Technical considerations:**
- Reuse existing `Assistant` methods (`avg_delta2()`, `calculate_blind_pick_score()`, etc.)
- Display in terminal or optionally export to file
- Consider adding visualization (histograms) if feasible

---

## Completed Features

### ✅ Tier List Generator (Completed 2025-10-15)
- Blind Pick tier lists (consistency-focused)
- Counter Pick tier lists (situational power-focused)
- Configurable weights and thresholds
- Integration with Pool Manager
- Normalized scoring (0-100)

### ✅ Code Refactoring (Completed 2025-10-15)
- Moved champion normalization functions from `config.py` to `constants.py`
- Improved code organization and separation of concerns
