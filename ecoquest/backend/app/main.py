import logging
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.services.carbon_calc import QuizInput, calculate_footprint
from app.services.ai_agent import generate_chat_stream
from app.database import (
    get_user_profile,
    create_or_update_profile,
    set_user_baseline,
    log_challenge_completion,
    get_leaderboard,
    create_post,
    get_posts,
    get_clubs,
    get_club_leaderboard,
    get_challenges,
    seed_challenges_if_empty,
    COL_CHALLENGES
)
from app.config import db
from pydantic import BaseModel, Field

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ecoquest.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan events - seeds challenges on startup.
    """
    logger.info("Starting EcoQuest Backend...")
    try:
        await seed_challenges_if_empty()
    except Exception as e:
        logger.error(f"Startup seeding failed: {e}")
    yield
    logger.info("Stopping EcoQuest Backend...")

app = FastAPI(
    title="EcoQuest API",
    description="Carbon Footprint Awareness Platform Backend",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request schemas
class QuizSubmitRequest(BaseModel):
    userId: str = Field(..., description="Stateless user identifier")
    userName: str = Field(..., description="User screen name")
    user_type: str = Field(..., description="User category, e.g., student, working professional, family")
    transport_type: str = Field(..., description="public, car, or bike_walk")
    transport_distance_km: float = Field(..., ge=0)
    diet_type: str = Field(..., description="meat, vegetarian, or vegan")
    electricity_kwh: float = Field(..., ge=0)

class PostSubmitRequest(BaseModel):
    userId: str
    userName: str
    action: str
    clubId: str | None = None
    imageUrl: str | None = None
    challengeId: str | None = None
    # For custom posts not linked to a preset challenge
    custom_co2_saved_kg: float = 0.0
    custom_action_points: int = 10

# API Endpoints

@app.get("/health")
async def health():
    return {"status": "healthy", "time": datetime.utcnow().isoformat()}

@app.post("/api/quiz")
async def submit_quiz(data: QuizSubmitRequest):
    """
    Calculates carbon footprint and stores baseline/current footprints in Firestore.
    """
    try:
        # 1. Deterministic Footprint calculation
        quiz_input = QuizInput(
            transport_type=data.transport_type,
            transport_distance_km=data.transport_distance_km,
            diet_type=data.diet_type,
            electricity_kwh=data.electricity_kwh
        )
        result = calculate_footprint(quiz_input)
        
        # 2. Check and set baseline atomically
        was_baseline_set = await set_user_baseline(data.userId, result.total_kg)
        
        # Retrieve profile to find baseline_kg
        profile = await get_user_profile(data.userId)
        
        # If profile doesn't exist, we create one now
        baseline_kg = result.total_kg
        if profile and profile.get("baseline_kg") is not None:
            baseline_kg = profile["baseline_kg"]
            
        # Recalculate vs national average and baseline comparison percentages
        vs_national_avg_pct = result.vs_national_avg_pct
        
        # Update user profile current state
        profile_update = {
            "userId": data.userId,
            "userName": data.userName,
            "user_type": data.user_type,
            "current_kg": result.total_kg,
            "breakdown": {
                "transport": result.breakdown.transport,
                "diet": result.breakdown.diet,
                "electricity": result.breakdown.electricity
            },
            "breakdown_pct": {
                "transport": result.breakdown_pct.transport,
                "diet": result.breakdown_pct.diet,
                "electricity": result.breakdown_pct.electricity
            },
            "vs_national_avg_pct": vs_national_avg_pct,
            "last_updated": datetime.utcnow()
        }
        
        # If user profile is completely new, initialize completed_challenges and action_points
        if not profile:
            profile_update["action_points"] = 0
            profile_update["completed_challenges"] = 0
            profile_update["baseline_kg"] = result.total_kg
            
        await create_or_update_profile(data.userId, profile_update)
        
        # Build return schema
        return {
            "total_kg": result.total_kg,
            "breakdown": profile_update["breakdown"],
            "breakdown_pct": profile_update["breakdown_pct"],
            "vs_national_avg_pct": vs_national_avg_pct,
            "baseline_set": was_baseline_set
        }
    except Exception as e:
        logger.error(f"Quiz submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/challenges")
async def get_active_challenges():
    """
    Retrieve all challenges available to users.
    """
    try:
        challenges = await get_challenges()
        return challenges
    except Exception as e:
        logger.error(f"Failed to fetch challenges: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve challenges")

@app.get("/api/leaderboard")
async def get_global_leaderboard():
    """
    Get top 10 users ranked by composite eco score.
    """
    try:
        leaderboard = await get_leaderboard()
        return leaderboard
    except Exception as e:
        logger.error(f"Failed to fetch leaderboard: {e}")
        raise HTTPException(status_code=500, detail="Failed to build leaderboard")

@app.get("/api/chat/stream")
async def chat_stream(
    userId: str = Query(..., description="User ID"),
    prompt: str = Query(..., description="Question for EcoBuddy")
):
    """
    SSE Stream endpoint for EcoBuddy.
    Retrieves user context to pass to Gemini-2.5-flash.
    """
    profile = await get_user_profile(userId)
    if not profile:
        # Fallback profile context if quiz is not taken yet
        profile = {
            "current_kg": 416.0,
            "total_kg": 416.0,
            "breakdown": {"transport": 100.0, "diet": 120.0, "electricity": 196.0},
            "vs_national_avg_pct": 0.0,
            "completed_challenges": 0,
            "user_type": "student",
            "userName": "New Eco Ranger"
        }
        
    return StreamingResponse(
        generate_chat_stream(prompt, profile),
        media_type="text/event-stream"
    )

@app.post("/api/posts")
async def submit_post(data: PostSubmitRequest):
    """
    Submit action to community feed. Handles challenge completion if challengeId is provided.
    """
    try:
        action_points = data.custom_action_points
        co2_saved_kg = data.custom_co2_saved_kg
        
        # If post is tied to a preset challenge, fetch its definitions
        if data.challengeId:
            challenge_ref = db.collection(COL_CHALLENGES).document(data.challengeId)
            challenge_doc = await challenge_ref.get()
            if challenge_doc.exists:
                challenge_data = challenge_doc.to_dict()
                action_points = challenge_data.get("action_points", action_points)
                co2_saved_kg = challenge_data.get("co2_saved_kg", co2_saved_kg)
                
                # Log completion log in subcollection
                today_str = datetime.utcnow().strftime("%Y-%m-%d")
                await log_challenge_completion(
                    user_id=data.userId,
                    challenge_id=data.challengeId,
                    date_str=today_str,
                    points=action_points,
                    co2_saved=co2_saved_kg
                )
            else:
                logger.warning(f"Challenge ID {data.challengeId} not found in database.")
        else:
            # For direct custom logging, still increment user's points
            user_ref = db.collection("users").document(data.userId)
            await user_ref.set({
                "action_points": firestore.Increment(action_points)
            }, merge=True)

        post_data = {
            "userId": data.userId,
            "userName": data.userName,
            "clubId": data.clubId,
            "action": data.action,
            "imageUrl": data.imageUrl,
            "co2_saved_kg": co2_saved_kg,
            "action_points": action_points
        }
        
        new_post = await create_post(post_data)
        return new_post
    except Exception as e:
        logger.error(f"Post submission failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/posts")
async def get_community_feed(limit: int = Query(25, ge=1, le=100)):
    """
    Get community feed posts ordered reverse-chronologically.
    """
    try:
        posts = await get_posts(limit)
        return posts
    except Exception as e:
        logger.error(f"Failed to fetch posts: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch feed")

@app.get("/api/clubs")
async def get_eco_clubs():
    """
    Retrieve running list of Eco Clubs.
    """
    try:
        clubs = await get_clubs()
        # Seed default clubs if none exist
        if len(clubs) == 0:
            default_clubs = [
                {"id": "green-campus", "name": "Green Campus Network", "description": "Students and faculty leading sustainability campaigns on campus.", "total_action_points": 0, "total_co2_saved_kg": 0.0, "member_count": 0},
                {"id": "clean-commuters", "name": "Clean Commuters Club", "description": "Advocating for bike lanes, walking routes, and electric vehicles.", "total_action_points": 0, "total_co2_saved_kg": 0.0, "member_count": 0},
                {"id": "zero-waste-warriors", "name": "Zero-Waste Warriors", "description": "Composting, recycling, and packaging-free living support network.", "total_action_points": 0, "total_co2_saved_kg": 0.0, "member_count": 0}
            ]
            for club in default_clubs:
                await db.collection("clubs").document(club["id"]).set(club)
            clubs = default_clubs
        return clubs
    except Exception as e:
        logger.error(f"Failed to fetch clubs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch clubs")

@app.get("/api/clubs/{clubId}/leaderboard")
async def get_club_ranking(clubId: str):
    """
    Retrieve top 10 members by action points in a club.
    """
    try:
        leaderboard = await get_club_leaderboard(clubId)
        return leaderboard
    except Exception as e:
        logger.error(f"Failed to fetch club leaderboard for {clubId}: {e}")
        raise HTTPException(status_code=500, detail="Failed to build club leaderboard")
