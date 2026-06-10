import json
import logging
from app.config import get_ai_model

logger = logging.getLogger("ecoquest.ai_agent")

SYSTEM_PROMPT = (
    "You are EcoBuddy, a hyper-personalized sustainability coach embedded in the EcoQuest platform.\n\n"
    "Rules you must follow in every response:\n"
    "1. Base ALL advice strictly on the user's profile data provided. Never give generic advice.\n"
    "2. If the user is a student/hostel resident, NEVER recommend solar panels, EV purchases, or home renovations. Instead: appliance habits, campus initiatives, reusable containers, local cleanups.\n"
    "3. For every concrete action you recommend, calculate and state the approximate monthly CO2 saving in kg.\n"
    "4. Be conversational, encouraging, and specific. No bullet-point dumps.\n"
    "5. If the user's footprint is already below national average, acknowledge it and focus on maintaining + community influence."
)

async def generate_chat_stream(prompt: str, profile_data: dict):
    """
    Asynchronously streams responses from gemini-2.5-flash via SSE.
    """
    try:
        # Resolve footprint values safely
        total_kg = profile_data.get("current_kg")
        if total_kg is None:
            total_kg = profile_data.get("total_kg", 416.0)
            
        db_breakdown = profile_data.get("breakdown", {})
        breakdown_transport = db_breakdown.get("transport", 0.0)
        breakdown_diet = db_breakdown.get("diet", 0.0)
        breakdown_electricity = db_breakdown.get("electricity", 0.0)
        
        vs_national_avg_pct = profile_data.get("vs_national_avg_pct", 0.0)
        completed_challenges = profile_data.get("completed_challenges", 0)
        user_type = profile_data.get("user_type", "student")
        
        # Inject exact user profile context verbatim
        user_context = f"""
User Profile:
- Monthly footprint: {total_kg} kg CO2
- Breakdown: Transport {breakdown_transport} kg, Diet {breakdown_diet} kg, Electricity {breakdown_electricity} kg
- vs National Average: {vs_national_avg_pct}%
- Completed challenges this month: {completed_challenges}
- User type: {user_type}  # e.g. "student", "working professional", "family"
"""
        
        full_prompt = f"{user_context}\n\nUser Question: {prompt}"
        
        # Instantiate Model with System Instructions
        model = get_ai_model(system_instruction=SYSTEM_PROMPT)
        
        logger.info(f"Initiating Vertex AI streaming for prompt. Context length: {len(user_context)}")
        
        # Streaming API call
        response_stream = await model.generate_content_async(
            contents=full_prompt,
            stream=True
        )
        
        async for response in response_stream:
            text_chunk = response.text
            if text_chunk:
                yield f"data: {json.dumps({'chunk': text_chunk})}\n\n"
                
        # Send termination chunk
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"Error in Vertex AI chat generation stream: {e}")
        error_msg = f"Oops! I encountered an error connecting to my AI core: {str(e)}"
        yield f"data: {json.dumps({'chunk': error_msg})}\n\n"
        yield "data: [DONE]\n\n"
