import asyncio
import random
import time
import uuid
from typing import Dict, Any, Callable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import async_session, User, Transaction
from app.cache import check_cooldown, set_cooldown, check_duplicate, set_duplicate_lock

# Global active listener queues (consumed by SSE endpoints)
active_listeners = set()

async def broadcast_event(type: str, data: Any):
    """Helper to broadcast real-time events to all SSE active connections"""
    event = {"type": type, "data": data}
    for listener in list(active_listeners):
        try:
            listener.put_nowait(event)
        except Exception:
            pass

class UrbanSimulator:
    def __init__(self):
        self.is_running = False
        self.rate_per_minute = 120
        self.sim_task = None
        self.users = [
            "alpha_cleaner", "nature_lover", "recycle_queen", "city_hero", 
            "green_knight", "street_sweeper", "eco_pathfinder", "urban_guardian",
            "waste_watcher", "clean_air_advocate", "sust_champion", "zero_waste_warrior"
        ]
        self.city_center = {"lat": 17.3850, "lng": 78.4867}

    def start(self, rate: int):
        if self.is_running:
            self.stop()
        self.is_running = True
        self.rate_per_minute = rate
        self.sim_task = asyncio.create_task(self._simulation_loop())
        print(f"[Simulator] Started concurrent traffic loop at {self.rate_per_minute} reports/min.")

    def stop(self):
        self.is_running = False
        if self.sim_task:
            self.sim_task.cancel()
            self.sim_task = None
        print("[Simulator] Stopped concurrent traffic loop.")

    def update_rate(self, rate: int):
        self.rate_per_minute = rate
        if self.is_running:
            self.start(rate)

    async def _simulation_loop(self):
        try:
            while self.is_running:
                # Calculate interval delay based on rate per minute
                delay = 60.0 / self.rate_per_minute
                await asyncio.sleep(delay)
                
                # Run simulated citizen action in background
                asyncio.create_task(self.generate_simulated_report())
        except asyncio.CancelledError:
            pass

    async def generate_simulated_report(self):
        random_user = random.choice(self.users)
        
        # Grid lat/lng offsets within ~2km of center
        lat_offset = (random.random() - 0.5) * 0.04
        lng_offset = (random.random() - 0.5) * 0.04
        coordinates = {
            "lat": round(self.city_center["lat"] + lat_offset, 6),
            "lng": round(self.city_center["lng"] + lng_offset, 6)
        }

        # Submissions roll logic
        # 60% Recyclable, 35% Non-recyclable, 5% Spoof (duplicate)
        roll = random.random()
        classification = "recyclable"
        is_spoof = False

        if roll > 0.60:
            classification = "non-recyclable"

        image_hash = f"hash_{random.randint(100000, 999999)}"

        # Determine simulated image_url based on category
        if classification == "recyclable":
            image_url = "/assets/recycle_box.png"
        else:
            image_url = "/assets/clean_bin.png"

        # Check Cache Rate-limiting
        is_allowed, sec_left = await check_cooldown(random_user, 15)
        if not is_allowed:
            # Broadcast instant blocked event
            await broadcast_event("simulator-event", {
                "type": "rejected_instant",
                "username": random_user,
                "classification": classification,
                "coordinates": coordinates,
                "message": f"Submission blocked. Cooldown active. Wait {sec_left} seconds.",
                "timestamp": int(time.time() * 1000)
            })
            return

        # Check Cache Duplicate Spoof (Disabled)
        is_dup = False
        if is_dup:
            tx_id = str(uuid.uuid4())
            now_ms = int(time.time() * 1000)
            
            async with async_session() as session:
                # Add spoof reject transaction logs to DB
                new_tx = Transaction(
                    id=tx_id,
                    username=random_user,
                    image_hash=image_hash,
                    classification=classification,
                    status="Spoof Rejected",
                    status_reason="Duplicate image hash detected (Anti-Spoofing)",
                    timestamp=now_ms,
                    lat=coordinates["lat"],
                    lng=coordinates["lng"],
                    reward_points=0,
                    image_url=image_url
                )
                session.add(new_tx)
                await session.commit()

                # Set cooldown to block fast attempts
                await set_cooldown(random_user, 15)

                tx_data = {
                    "id": tx_id,
                    "username": random_user,
                    "imageHash": image_hash,
                    "classification": classification,
                    "status": "Spoof Rejected",
                    "timestamp": now_ms,
                    "rewardPoints": 0,
                    "imageUrl": image_url
                }
                
                await broadcast_event("simulator-event", {
                    "type": "rejected_instant",
                    "username": random_user,
                    "classification": classification,
                    "coordinates": coordinates,
                    "message": "Spoofing attempt detected. Duplicate disposal signature blocked.",
                    "transaction": tx_data,
                    "timestamp": now_ms
                })
            return

        # Process valid submission
        tx_id = str(uuid.uuid4())
        now_ms = int(time.time() * 1000)
        reward_points = 50 if classification == "recyclable" else (20 if classification == "non-recyclable" else 0)

        async with async_session() as session:
            # 1. Ensure user exists
            q = await session.execute(select(User).filter_by(username=random_user))
            user = q.scalar_one_or_none()
            if not user:
                user = User(username=random_user, points=0, level=1, badges="Green Novice")
                session.add(user)

            # 2. Insert transaction
            new_tx = Transaction(
                id=tx_id,
                username=random_user,
                image_hash=image_hash,
                classification=classification,
                status="Verification Pending",
                timestamp=now_ms,
                lat=coordinates["lat"],
                lng=coordinates["lng"],
                reward_points=reward_points,
                image_url=image_url
            )
            session.add(new_tx)
            await session.commit()

            # Set locks
            await set_cooldown(random_user, 15)
            await set_duplicate_lock(image_hash, 60)

            tx_data = {
                "id": tx_id,
                "username": random_user,
                "imageHash": image_hash,
                "classification": classification,
                "status": "Verification Pending",
                "timestamp": now_ms,
                "reward_points": reward_points,
                "imageUrl": image_url
            }

            # Broadcast Submission Event
            await broadcast_event("simulator-event", {
                "type": "submission",
                "username": random_user,
                "classification": classification,
                "coordinates": coordinates,
                "transaction": tx_data,
                "timestamp": now_ms
            })

            # Simulate pipeline completion after 1.5 seconds
            asyncio.create_task(self.finalize_verification(tx_id, classification not in ["invalid_disposal", "unknown_object"]))

    async def finalize_verification(self, tx_id: str, approve: bool):
        await asyncio.sleep(1.5)
        
        async with async_session() as session:
            # Get transaction
            tx_q = await session.execute(select(Transaction).filter_by(id=tx_id))
            tx = tx_q.scalar_one_or_none()
            if not tx or tx.status != "Verification Pending":
                return

            # Get user
            user_q = await session.execute(select(User).filter_by(username=tx.username))
            user = user_q.scalar_one_or_none()
            if not user:
                return

            if approve and tx.classification != "invalid_disposal" and tx.classification != "unknown_object":
                tx.status = "Points Awarded"
                user.points += tx.reward_points
                
                # Prog level logic
                if user.points >= 800:
                    user.level = 4
                elif user.points >= 400:
                    user.level = 3
                elif user.points >= 150:
                    user.level = 2
                else:
                    user.level = 1
                
                # Prog badges checks
                badges = user.get_badges_list()
                
                # Check sort master
                if "Sort Master" not in badges and tx.classification == "recyclable":
                    badges.append("Sort Master")
                
                # Check waste buster
                if "Waste Buster" not in badges:
                    # Count successful cleans
                    cnt_q = await session.execute(
                        select(Transaction).filter(
                            Transaction.username == user.username,
                            Transaction.status == "Points Awarded"
                        )
                    )
                    clean_cnt = len(cnt_q.scalars().all())
                    if clean_cnt >= 3:
                        badges.append("Waste Buster")
                
                # Check eco legend
                if "Eco Legend" not in badges and user.level >= 4:
                    badges.append("Eco Legend")
                
                user.set_badges_list(badges)
            else:
                tx.status = "Rejected"
                if tx.classification == "invalid_disposal":
                    tx.status_reason = "Human presence detected. Not a valid waste item."
                elif tx.classification == "unknown_object":
                    tx.status_reason = "Unrecognized item. For the mock AI prototype, please rename your file to contain a waste keyword (e.g. 'bottle.jpg', 'trash_bin.jpg')."
                else:
                    tx.status_reason = "Verification failed."
                tx.reward_points = 0

            await session.commit()

            tx_data = {
                "id": tx.id,
                "username": tx.username,
                "imageHash": tx.image_hash,
                "classification": tx.classification,
                "status": tx.status,
                "statusReason": tx.status_reason,
                "timestamp": tx.timestamp,
                "rewardPoints": tx.reward_points,
                "imageUrl": tx.image_url
            }

            user_data = {
                "username": user.username,
                "points": user.points,
                "level": user.level,
                "badges": user.get_badges_list()
            }

            # Broadcast Complete Event
            await broadcast_event("simulator-event", {
                "type": "verification_completed",
                "transaction": tx_data,
                "user": user_data,
                "timestamp": int(time.time() * 1000)
            })

    async def get_stats_summary(self) -> Dict[str, Any]:
        async with async_session() as session:
            # Query db totals
            tx_q = await session.execute(select(Transaction))
            all_txs = tx_q.scalars().all()
            
            total_tx = len(all_txs)
            pending = len([t for t in all_txs if t.status == "Verification Pending"])
            awarded = len([t for t in all_txs if t.status == "Points Awarded"])
            rejected = len([t for t in all_txs if t.status == "Rejected"])
            spoofs = len([t for t in all_txs if t.status == "Spoof Rejected"])
            
            # CPU load calculation
            base_cpu = 5
            rate_load = self.rate_per_minute / 10
            queue_load = pending * 2.5
            cpu_load = min(round(base_cpu + rate_load + queue_load), 99)

            return {
                "isRunning": self.is_running,
                "ratePerMinute": self.rate_per_minute,
                "totalTransactions": total_tx,
                "pendingTransactions": pending,
                "awardedTransactions": awarded,
                "rejectedTransactions": rejected,
                "spoofTransactions": spoofs,
                "cpuLoad": cpu_load
            }

# Instantiate global simulator
simulator = UrbanSimulator()
