"""LeagueStats Coach API Server.

FastAPI application providing REST API for champion analysis.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..config import settings

# Import routes
from .routes import health, champions, matchups, tier_list, analysis

app = FastAPI(
    title="LeagueStats Coach API",
    description="REST API for League of Legends champion analysis and draft recommendations",
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(health.router)
app.include_router(champions.router, prefix="/api", tags=["champions"])
app.include_router(matchups.router, prefix="/api", tags=["matchups"])
app.include_router(tier_list.router, prefix="/api", tags=["tier-list"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    print(f"🚀 LeagueStats Coach API v{settings.app_version} starting...")
    print(f"📊 Environment: {settings.app_env}")
    print(f"🗄️  Database: Connected to PostgreSQL")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    print("👋 LeagueStats Coach API shutting down...")
