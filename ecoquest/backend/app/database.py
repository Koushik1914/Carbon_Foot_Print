import logging
from datetime import datetime
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from app.config import db

logger = logging.getLogger("ecoquest.database")

# Collection Namespace Constants
COL_USERS = "users"
COL_CHALLENGES = "challenges"
COL_POSTS = "posts"
COL_CLUBS = "clubs"

async def get_user_profile(user_id: str) -> dict | None:
    """
    Retrieve user profile from Firestore.
    """
    try:
        doc_ref = db.collection(COL_USERS).document(user_id)
        doc = await doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.error(f"Error fetching user profile {user_id}: {e}")
        return None

async def create_or_update_profile(user_id: str, profile_data: dict) -> dict:
    """
    Create or update user profile details.
    """
    try:
        doc_ref = db.collection(COL_USERS).document(user_id)
        # We perform a merge write to avoid overwriting existing fields (like baseline)
        await doc_ref.set(profile_data, merge=True)
        updated_doc = await doc_ref.get()
        return updated_doc.to_dict()
    except Exception as e:
        logger.error(f"Error updating user profile {user_id}: {e}")
        raise e

async def set_user_baseline(user_id: str, baseline_kg: float) -> bool:
    """
    Sets the user's baseline footprint ONLY if it is not already set.
    Returns True if baseline was set, False if it already existed.
    """
    try:
        doc_ref = db.collection(COL_USERS).document(user_id)
        
        # Transaction to ensure atomic check-and-set
        @firestore.transactional
        def _set_baseline_tx(transaction, doc_reference, val_kg):
            snapshot = doc_reference.get(transaction=transaction)
            if snapshot.exists:
                data = snapshot.to_dict()
                if data.get("baseline_kg") is not None:
                    return False
            
            transaction.set(doc_reference, {
                "baseline_kg": val_kg,
                "baseline_set_at": datetime.utcnow()
            }, merge=True)
            return True

        transaction = db.transaction()
        return _set_baseline_tx(transaction, doc_ref, baseline_kg)
    except Exception as e:
        logger.error(f"Error setting baseline for {user_id}: {e}")
        # Fallback to direct check if transaction fails
        doc = await db.collection(COL_USERS).document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            if data.get("baseline_kg") is not None:
                return False
        await db.collection(COL_USERS).document(user_id).set({
            "baseline_kg": baseline_kg,
            "baseline_set_at": datetime.utcnow()
        }, merge=True)
        return True

async def log_challenge_completion(user_id: str, challenge_id: str, date_str: str, points: int, co2_saved: float) -> dict:
    """
    Log completion of a challenge.
    Increments user action points, adds to completed challenges count, and creates history log.
    Path: users/{userId}/history/{YYYY-MM-DD}/challenges/{challengeId}
    """
    try:
        # 1. Write history log
        log_ref = db.collection(COL_USERS).document(user_id) \
                    .collection("history").document(date_str) \
                    .collection("challenges").document(challenge_id)
        
        await log_ref.set({
            "completed_at": datetime.utcnow(),
            "action_points_awarded": points,
            "co2_saved_kg": co2_saved
        })

        # 2. Update user aggregates atomically
        user_ref = db.collection(COL_USERS).document(user_id)
        await user_ref.set({
            "action_points": firestore.Increment(points),
            "completed_challenges": firestore.Increment(1)
        }, merge=True)

        user_doc = await user_ref.get()
        return user_doc.to_dict()
    except Exception as e:
        logger.error(f"Error logging challenge completion for {user_id}: {e}")
        raise e

async def get_leaderboard() -> list:
    """
    Retrieves all users with a baseline, computes composite scores,
    and returns top 10 ranked users.
    rank_score = (improvement_pct * 0.6) + (normalized_action_points * 0.4)
    improvement_pct = ((baseline_kg - current_kg) / baseline_kg) * 100
    """
    try:
        users_ref = db.collection(COL_USERS)
        # Fetch all users
        docs = await users_ref.get()
        
        valid_users = []
        max_points = 0
        
        for doc in docs:
            data = doc.to_dict()
            data["userId"] = doc.id
            baseline = data.get("baseline_kg")
            current = data.get("current_kg")
            
            # Users with no baseline are excluded
            if baseline is not None and baseline > 0 and current is not None:
                action_points = data.get("action_points", 0)
                if action_points > max_points:
                    max_points = action_points
                valid_users.append(data)
                
        # Calculate scores
        leaderboard = []
        for user in valid_users:
            baseline = user["baseline_kg"]
            current = user["current_kg"]
            action_points = user.get("action_points", 0)
            
            # Calculate improvement % (higher reduction is better)
            improvement_pct = ((baseline - current) / baseline) * 100
            
            # Normalize action points against max_points
            normalized_points = 0.0
            if max_points > 0:
                normalized_points = (action_points / max_points) * 100
                
            rank_score = (improvement_pct * 0.6) + (normalized_points * 0.4)
            
            leaderboard.append({
                "userId": user["userId"],
                "userName": user.get("userName", "Eco Ranger"),
                "baseline_kg": baseline,
                "current_kg": current,
                "improvement_pct": round(improvement_pct, 2),
                "action_points": action_points,
                "normalized_action_points": round(normalized_points, 2),
                "rank_score": round(rank_score, 2),
                "user_type": user.get("user_type", "individual")
            })
            
        # Sort descending by rank_score
        leaderboard.sort(key=lambda x: x["rank_score"], reverse=True)
        return leaderboard[:10]
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {e}")
        return []

async def create_post(post_data: dict) -> dict:
    """
    Creates a new community post. If clubId is provided, updates club aggregations.
    Post Schema matches Firestore posts/{postId}
    """
    try:
        post_ref = db.collection(COL_POSTS).document()
        post_id = post_ref.id
        
        # Structure the post data
        full_post = {
            "id": post_id,
            "userId": post_data["userId"],
            "userName": post_data["userName"],
            "clubId": post_data.get("clubId"),
            "action": post_data["action"],
            "imageUrl": post_data.get("imageUrl"),
            "co2_saved_kg": float(post_data.get("co2_saved_kg", 0.0)),
            "action_points": int(post_data.get("action_points", 0)),
            "timestamp": datetime.utcnow(),
            "likes": 0
        }
        
        await post_ref.set(full_post)
        
        # If posting to a club, update club aggregates atomically
        club_id = post_data.get("clubId")
        if club_id:
            # 1. Update/Create Club Member stats
            member_ref = db.collection(COL_CLUBS).document(club_id) \
                           .collection("members").document(post_data["userId"])
            
            member_doc = await member_ref.get()
            is_new_member = not member_doc.exists
            
            if is_new_member:
                await member_ref.set({
                    "userId": post_data["userId"],
                    "userName": post_data["userName"],
                    "action_points": post_data.get("action_points", 0),
                    "joined_at": datetime.utcnow()
                })
            else:
                await member_ref.update({
                    "action_points": firestore.Increment(post_data.get("action_points", 0))
                })
                
            # 2. Update Club overall aggregates
            club_ref = db.collection(COL_CLUBS).document(club_id)
            club_doc = await club_ref.get()
            
            club_update = {
                "total_action_points": firestore.Increment(post_data.get("action_points", 0)),
                "total_co2_saved_kg": firestore.Increment(float(post_data.get("co2_saved_kg", 0.0)))
            }
            if is_new_member:
                club_update["member_count"] = firestore.Increment(1)
                
            if not club_doc.exists:
                # Initialize club details
                club_name = club_id.replace("-", " ").title()
                await club_ref.set({
                    "id": club_id,
                    "name": club_name,
                    "description": f"Official club for {club_name} enthusiasts.",
                    "total_action_points": post_data.get("action_points", 0),
                    "total_co2_saved_kg": float(post_data.get("co2_saved_kg", 0.0)),
                    "member_count": 1,
                    "created_at": datetime.utcnow()
                })
            else:
                await club_ref.update(club_update)
                
        return full_post
    except Exception as e:
        logger.error(f"Error creating post: {e}")
        raise e

async def get_posts(limit: int = 50) -> list:
    """
    Retrieve reverse-chronological feed posts.
    """
    try:
        posts_ref = db.collection(COL_POSTS).order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit)
        docs = await posts_ref.get()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.error(f"Error retrieving posts: {e}")
        return []

async def get_clubs() -> list:
    """
    Retrieve all available clubs and their collective metrics.
    """
    try:
        clubs_ref = db.collection(COL_CLUBS)
        docs = await clubs_ref.get()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.error(f"Error retrieving clubs: {e}")
        return []

async def get_club_leaderboard(club_id: str) -> list:
    """
    Returns top 10 members in a club by action_points.
    """
    try:
        members_ref = db.collection(COL_CLUBS).document(club_id).collection("members")
        query = members_ref.order_by("action_points", direction=firestore.Query.DESCENDING).limit(10)
        docs = await query.get()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.error(f"Error retrieving club leaderboard for {club_id}: {e}")
        return []

async def get_challenges() -> list:
    """
    Retrieve list of active challenges.
    """
    try:
        challenges_ref = db.collection(COL_CHALLENGES)
        docs = await challenges_ref.get()
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.error(f"Error retrieving challenges: {e}")
        return []

async def seed_challenges_if_empty() -> None:
    """
    Seeds default challenges if challenges collection is empty.
    """
    try:
        challenges_ref = db.collection(COL_CHALLENGES)
        docs = await challenges_ref.limit(1).get()
        if len(docs) > 0:
            return
            
        default_challenges = [
            {
                "id": "no-car-monday",
                "title": "No-Car Monday",
                "description": "Commute by public transport, walking, or biking today.",
                "frequency": "weekly",
                "action_points": 50,
                "co2_saved_kg": 5.0
            },
            {
                "id": "go-vegan-day",
                "title": "Vegan for a Day",
                "description": "Eat only plant-based meals today.",
                "frequency": "daily",
                "action_points": 30,
                "co2_saved_kg": 3.0
            },
            {
                "id": "unplug-idle",
                "title": "Unplug Idle Devices",
                "description": "Unplug chargers and appliances when not in use.",
                "frequency": "daily",
                "action_points": 15,
                "co2_saved_kg": 1.2
            },
            {
                "id": "campus-cleanup",
                "title": "Local Cleanups",
                "description": "Spend 30 minutes cleaning up litter in your community.",
                "frequency": "weekly",
                "action_points": 40,
                "co2_saved_kg": 0.5
            }
        ]
        
        for challenge in default_challenges:
            await challenges_ref.document(challenge["id"]).set(challenge)
        logger.info("Default challenges seeded successfully.")
    except Exception as e:
        logger.error(f"Error seeding challenges: {e}")
