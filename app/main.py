import os
import json
import asyncio
import time
import uuid
from fastapi import FastAPI, Depends, UploadFile, File, Form, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.database import init_db, async_session, User, Transaction
from app.auth import get_current_user
from app.cache import check_cooldown, set_cooldown, check_duplicate, set_duplicate_lock, clear_cache
from app.vision import classify_disposal
from app.simulator import simulator, active_listeners, broadcast_event

app = FastAPI(title="CleanMyCity API", version="1.0.0")

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # Initialize SQLAlchemy database tables
    await init_db()
    # Ensure uploads directory exists
    os.makedirs("app/templates/uploads", exist_ok=True)
    print("[Main] Async Database Initialized.")

# 1. Server-Sent Events (SSE) Stream
@app.get("/api/events")
async def sse_events(request: Request):
    client_queue = asyncio.Queue()
    active_listeners.add(client_queue)

    async def event_generator():
        try:
            while True:
                # Check for disconnection
                if await request.is_disconnected():
                    break
                try:
                    # Wait for next event in queue with timeout to keep connection responsive
                    event = await asyncio.wait_for(client_queue.get(), timeout=1.0)
                    yield {
                        "data": json.dumps(event)
                    }
                    client_queue.task_done()
                except asyncio.TimeoutError:
                    # Heartbeat to keep connection alive
                    yield {
                        "event": "heartbeat",
                        "data": ""
                    }
        except asyncio.CancelledError:
            pass
        finally:
            active_listeners.discard(client_queue)

    return EventSourceResponse(event_generator())

# 2. REST API endpoints

# GET /api/user/{username}
@app.get("/api/user/{username}")
async def get_user_profile(username: str):
    clean_username = username.strip().lower()
    async with async_session() as session:
        q = await session.execute(select(User).filter_by(username=clean_username))
        user = q.scalar_one_or_none()
        if not user:
            # Create user on the fly (equivalent to JS behaviour)
            user = User(username=clean_username, points=0, level=1, badges="Green Novice")
            session.add(user)
            await session.commit()
            await session.refresh(user)

        return {
            "username": user.username,
            "points": user.points,
            "level": user.level,
            "badges": user.get_badges_list(),
            "lastSubmissionTime": user.last_submission_time
        }

# GET /api/leaderboard
@app.get("/api/leaderboard")
async def get_leaderboard():
    async with async_session() as session:
        q = await session.execute(select(User).order_by(User.points.desc()))
        users = q.scalars().all()
        return [
            {
                "username": u.username,
                "points": u.points,
                "level": u.level,
                "badges": u.get_badges_list()
            }
            for u in users
        ]

# GET /api/ledger
@app.get("/api/ledger")
async def get_ledger():
    async with async_session() as session:
        q = await session.execute(select(Transaction).order_by(Transaction.timestamp.desc()).limit(100))
        txs = q.scalars().all()
        return [
            {
                "id": t.id,
                "username": t.username,
                "imageHash": t.image_hash,
                "classification": t.classification,
                "status": t.status,
                "statusReason": t.status_reason,
                "timestamp": t.timestamp,
                "rewardPoints": t.reward_points,
                "imageUrl": t.image_url
            }
            for t in txs
        ]

# GET /api/dashboard/stats
@app.get("/api/dashboard/stats")
async def get_stats():
    return await simulator.get_stats_summary()

# POST /api/simulator/control
@app.post("/api/simulator/control")
async def control_simulator(request: Request):
    payload = await request.json()
    action = payload.get("action")
    rate = payload.get("rate", 120)

    if action == "start":
        simulator.start(rate)
        stats = await simulator.get_stats_summary()
        return {"message": "Simulator started", "stats": stats}
    elif action == "stop":
        simulator.stop()
        stats = await simulator.get_stats_summary()
        return {"message": "Simulator stopped", "stats": stats}
    elif action == "rate":
        simulator.update_rate(rate)
        stats = await simulator.get_stats_summary()
        return {"message": f"Simulator rate updated to {rate}/min", "stats": stats}
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'start', 'stop', or 'rate'.")

# POST /api/database/clear
@app.post("/api/database/clear")
async def clear_database():
    async with async_session() as session:
        # Purge both tables
        await session.execute(delete(Transaction))
        await session.execute(delete(User))
        await session.commit()
    
    # Reset Cache
    await clear_cache()

    # Re-initialize citizen_zero
    async with async_session() as session:
        cz = User(username="citizen_zero", points=120, level=1, badges="Green Novice")
        session.add(cz)
        await session.commit()

    return {"message": "Database reset successfully"}

# POST /api/disposal/submit (Authenticated File Upload Endpoint)
@app.post("/api/disposal/submit")
async def submit_disposal(
    file: UploadFile = File(...),
    username: str = Depends(get_current_user),
    lat: float = Form(0.0),
    lng: float = Form(0.0)
):
    # Cooldown checks
    is_allowed, sec_left = await check_cooldown(username, 15)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Submission blocked. Cooldown active. Please wait {sec_left} seconds."
        )

    # Read file bytes
    file_bytes = await file.read()
    
    # Process image through OpenCV & simulated TF core
    classification, confidence, img_hash, framing_passed = await classify_disposal(file_bytes, file.filename)

    # Generate unique ID for this transaction and save the file permanently
    tx_id = str(uuid.uuid4())
    _, ext = os.path.splitext(file.filename)
    if not ext:
        ext = ".png"
    image_filename = f"{tx_id}{ext}"
    image_filepath = os.path.join("app/templates/uploads", image_filename)
    
    try:
        with open(image_filepath, "wb") as buffer:
            buffer.write(file_bytes)
        image_url = f"/uploads/{image_filename}"
    except Exception as e:
        print(f"[Main] Save upload error: {e}")
        image_url = None

    # Check duplicates check (Anti-spoofing)
    is_dup = await check_duplicate(img_hash, 60)
    if is_dup:
        now_ms = int(time.time() * 1000)

        # Log duplicate spoof transaction to database
        async with async_session() as session:
            new_tx = Transaction(
                id=tx_id,
                username=username,
                image_hash=img_hash,
                classification=classification,
                status="Spoof Rejected",
                status_reason="Duplicate image hash detected (Anti-Spoofing)",
                timestamp=now_ms,
                lat=lat,
                lng=lng,
                reward_points=0,
                image_url=image_url
            )
            session.add(new_tx)
            await session.commit()
            
            # Enforce cooldown even on failure
            await set_cooldown(username, 15)

        tx_data = {
            "id": tx_id,
            "username": username,
            "imageHash": img_hash,
            "classification": classification,
            "status": "Spoof Rejected",
            "timestamp": now_ms,
            "rewardPoints": 0,
            "imageUrl": image_url
        }

        # Broadcast event
        await broadcast_event("citizen-event", {
            "type": "rejected_instant",
            "username": username,
            "classification": classification,
            "coordinates": {"lat": lat, "lng": lng},
            "message": "Spoofing attempt detected. Duplicate disposal signature blocked.",
            "transaction": tx_data,
            "timestamp": now_ms
        })

        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Spoofing attempt detected. Duplicate disposal signature blocked."
        )

    # Valid submission flow (Initial State: Verification Pending)
    now_ms = int(time.time() * 1000)
    reward_points = 50 if classification == "recyclable" else (20 if classification == "non-recyclable" else 0)

    async with async_session() as session:
        # Create transaction log
        new_tx = Transaction(
            id=tx_id,
            username=username,
            image_hash=img_hash,
            classification=classification,
            status="Verification Pending",
            timestamp=now_ms,
            lat=lat,
            lng=lng,
            reward_points=reward_points,
            image_url=image_url
        )
        session.add(new_tx)
        
        # Update user last submission time in DB
        q = await session.execute(select(User).filter_by(username=username))
        user = q.scalar_one_or_none()
        if user:
            user.last_submission_time = now_ms
        
        await session.commit()

    # Lock rate limit and signatures
    await set_cooldown(username, 15)
    await set_duplicate_lock(img_hash, 60)

    tx_data = {
        "id": tx_id,
        "username": username,
        "imageHash": img_hash,
        "classification": classification,
        "status": "Verification Pending",
        "timestamp": now_ms,
        "rewardPoints": reward_points,
        "imageUrl": image_url
    }

    # Broadcast Submission Event
    await broadcast_event("citizen-event", {
        "type": "submission",
        "username": username,
        "classification": classification,
        "coordinates": {"lat": lat, "lng": lng},
        "transaction": tx_data,
        "timestamp": now_ms
    })

    # Trigger Async Pipeline Completion Task (simulates verification pipeline delay)
    asyncio.create_task(simulator.finalize_verification(tx_id, classification not in ["invalid_disposal", "unknown_object"]))

    return {
        "message": "Disposal registered. Pending verification.",
        "transaction": tx_data
    }

# 3. MOUNT TEMPLATES AND STATIC FILES (Served as fallback)
app.mount("/", StaticFiles(directory="app/templates", html=True), name="static")
