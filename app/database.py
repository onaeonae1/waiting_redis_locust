# default
import os
import random
import string

# pip
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import text

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5432/waiting_db"
)

engine = create_async_engine(DATABASE_URL, echo=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with async_session() as session:
        yield session


def random_booth_name():
    return "Booth-" + "".join(random.choices(string.ascii_letters, k=5))


async def clear_waiting_data(redis: Redis):
    await redis.flushall()
    print("Redis & DB Waiting 데이터 초기화 완료")


async def initialize_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text("INSERT INTO booths (id, name) VALUES (1, :name1), (2, :name2)"),
            {
                "name1": random_booth_name(),
                "name2": random_booth_name(),
            },
        )
