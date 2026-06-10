# EcoQuest — Carbon Footprint Awareness Platform

## Chosen Vertical
**SustainTech & Climate Action (Gamified Awareness)**

## Problem Statement
Understanding and reducing personal greenhouse gas emissions is critical to combating climate change. However, individuals face multiple barriers:
1. **Generic Advice:** Most carbon footprint calculators provide flat, generalized feedback (e.g. "Install solar panels") that is inapplicable to student hostel residents or low-income urban professionals.
2. **Engagement Decay:** Static calculators are used once and abandoned; they lack ongoing tracking, community engagement, and gamified reinforcement.
3. **Unfair Competition:** Traditional carbon leaderboards rank users by absolute lowest footprint, penalizing individuals who start with high baselines or live in regions with carbon-intensive electricity grids.

EcoQuest solves these problems by providing:
- A pure deterministic, localized footprint calculator.
- A composite-scored, fair leaderboard prioritizing relative improvement.
- Atomically updated Eco Clubs and community action feed.
- An interactive, hyper-personalized AI Coach (EcoBuddy) powered by Vertex AI and Gemini.

---

## Architecture Overview
The platform leverages a serverless architecture deployed to Google Cloud Platform (GCP).

### ASCII System Diagram
```
+-----------------------------------------------------------------------------+
|                                  FRONTEND                                   |
|   Static SPA: HTML5 / CSS3 / Vanilla JS (EventSource SSE + Fetch API)       |
+------------------------------------+----------------------------------------+
                                     |
                                     | (JSON REST + SSE Stream)
                                     v
+-----------------------------------------------------------------------------+
|                            BACKEND (FastAPI API)                            |
|             Containerized App Running on Google Cloud Run                   |
+-----+------------------------------+----------------------------------+-----+
      |                              |                                  |
      | (Async Firestore SDK)        | (Vertex AI SDK)                  | (Deterministic)
      v                              v                                  v
+-----------+                  +-----------+                      +-----------+
| FIRESTORE |                  | VERTEX AI |                      |  CARBON   |
|  Native   |                  | Gemini    |                      | CALCULATOR|
|  Database |                  | 2.5 Flash |                      |  Engine   |
+-----------+                  +-----------+                      +-----------+
```

---

## Module Breakdown

### Module 1 — Carbon Footprint Calculator (`/api/quiz`)
Calculates the footprint using deterministic coefficients:
- **Transport:** Car (0.25 kg/km), Public Transit (0.1 kg/km), Walk/Bike (0.0 kg/km).
- **Diet:** Meat (120.0 kg/month), Vegetarian (45.0 kg/month), Vegan (30.0 kg/month).
- **Electricity:** 0.4 kg/kWh.
Baseline is set upon the first submission and remains immutable. Subsequent attempts update the user's current footprint.

### Module 2 — Challenge Engine & Leaderboard (`/api/challenges`, `/api/leaderboard`)
Maintains challenges (e.g., "No-Car Monday") in Firestore. Completions are recorded under `users/{userId}/history/{YYYY-MM-DD}/{challengeId}`.
The Leaderboard calculates rank using a composite equation:
$$\text{rank\_score} = (\text{improvement\_pct} \times 0.6) + (\text{normalized\_action\_points} \times 0.4)$$
Where:
- $\text{improvement\_pct} = \frac{\text{baseline} - \text{current}}{\text{baseline}} \times 100$
- $\text{normalized\_action\_points} = \frac{\text{user\_points}}{\text{max\_points\_on\_leaderboard}} \times 100$

### Module 3 — EcoBuddy AI Chat (`/api/chat/stream`)
Uses FastAPI `StreamingResponse` to push Server-Sent Events (SSE). The prompt context injects user type (e.g., student vs. working professional) to filter recommendations (e.g. no solar panels for students).

### Module 4 — Community Feed & Eco Clubs (`/api/posts`, `/api/clubs`)
Calculates atomic totals for Eco Clubs (`total_action_points`, `total_co2_saved_kg`, `member_count`) using Firestore transactions and `Increment` field operations to ensure data integrity under concurrent submissions.

---

## AI Design Decisions
1. **Server-Sent Events (SSE):** We chose SSE (`EventSource` in HTML5) rather than traditional polling or WebSockets. SSE is lightweight, operates over HTTP, natively auto-reconnects, and streams Gemini tokens in real-time, yielding a superior user experience with minimal server resource consumption.
2. **System Prompt Guardrails:** By embedding strict rule constraints directly into the system prompt, EcoBuddy refuses to suggest irrelevant capital-intensive installations (like EVs or heat pumps) to students and hostel residents, suggesting small, actionable campus activities instead. It also formats calculations directly into recommendations to establish credibility.

---

## Leaderboard Fairness Rationale
Standard carbon trackers rank users by absolute lowest emissions. This approach is inherently biased, rewarding individuals who already possess high-efficiency homes or have short commutes due to wealth, while penalizing those striving to make large improvements in difficult circumstances.
EcoQuest's composite algorithm scores users on **relative improvement (60%)** and **activity (40%)**. This encourages all users—regardless of where they start—to log actions and reduce their footprint, creating an inclusive and motivating competition.

---

## Local Development Setup

### Prerequisite
- Python 3.11 installed
- Google Cloud CLI configured with application default credentials (`gcloud auth application-default login`)

### Run Backend
1. Navigate to the backend folder:
   ```bash
   cd ecoquest/backend
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the development server:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
   ```

### Run Frontend
Simply open `ecoquest/frontend/index.html` in any web browser, or serve it using Python's built-in HTTP module:
```bash
cd ecoquest/frontend
python -m http.server 3000
```
Then visit `http://localhost:3000`.

---

## GCP Deployment Guide

Execute the idempotent deployment script. It will enable APIs, create the Native Firestore database, push your container to Artifact Registry via Cloud Build, and deploy to Cloud Run.

```bash
# Make script executable
chmod +x ecoquest/deploy.sh

# Deploy
export PROJECT_ID="ecoquest-499004"
export REGION="us-central1"
./ecoquest/deploy.sh
```

---

## Assumptions Made
1. **Stateless Identity:** User authentication uses client-configured header/body identifiers for simplicity. This simulates Multi-tenant users without the overhead of OAuth/JWT for the current scope.
2. **Indian Baseline:** Comparative metrics leverage India's national baseline of 416 kg CO2 monthly per capita.
3. **Stateless AI context:** User history context is injected via prompt templates directly on every API request.

---

## Future Improvements
1. **Dynamic Regional baselines:** Adjust comparing values based on the user's selected country or city database.
2. **Image recognition for actions:** Use Gemini's multimodal capabilities to verify challenge completion via user-uploaded photos.
3. **Offline support:** Implement service workers and IndexedDB storage on the frontend for offline quiz calculation and offline post queuing.
