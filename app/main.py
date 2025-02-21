from fastapi import FastAPI


from app.database import initialize_database, clear_waiting_data
from app.redis import get_redis_session
from app.routes import router

app = FastAPI()

app.include_router(router)


@app.on_event("startup")
async def startup_event():
    await initialize_database()

    redis_session = await get_redis_session()
    await clear_waiting_data(redis_session)
    await redis_session.close()
