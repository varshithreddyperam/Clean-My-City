import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Float
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///d:/Ai bases Wate management/cleanmycity.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(100), primary_key=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    badges: Mapped[str] = mapped_column(String(500), default="Green Novice")  # Comma-separated strings
    last_submission_time: Mapped[float] = mapped_column(Float, default=0.0)

    def get_badges_list(self):
        return [b.strip() for b in self.badges.split(",") if b.strip()]

    def set_badges_list(self, badges_list):
        self.badges = ",".join(badges_list)

class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    username: Mapped[str] = mapped_column(String(100))
    image_hash: Mapped[str] = mapped_column(String(100))
    classification: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="Verification Pending")
    timestamp: Mapped[float] = mapped_column(Float)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    reward_points: Mapped[int] = mapped_column(Integer, default=0)
    status_reason: Mapped[str] = mapped_column(String(200), nullable=True)
    image_url: Mapped[str] = mapped_column(String(200), nullable=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
