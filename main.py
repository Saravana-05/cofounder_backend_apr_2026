from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, profile, preferences, synapse, matches, ai
from app.database import engine, Base
from mangum import Mangum

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Cofounders Matrimony API",
    description="Startup cofounder matchmaking platform powered by structured profile data and psychometric compatibility",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(profile.router, prefix="/profile", tags=["Profile"])
app.include_router(preferences.router, prefix="/preferences", tags=["Preferences"])
app.include_router(synapse.router, prefix="/synapse-test", tags=["Synapse Test"])
app.include_router(matches.router, prefix="/matches", tags=["Matches"])
app.include_router(ai.router, prefix="/ai", tags=["AI Integration"])

@app.get("/")
async def root():
    return {"message": "Cofounders Matrimony API", "version": "1.0.0", "status": "active"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
# Lambda handler
handler = Mangum(app)