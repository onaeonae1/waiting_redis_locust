import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import redis.asyncio as redis

from app.models import Waiting
from app.schemas import (
    WaitingRequest,
    WaitingResponse,
    CancelWaitingRequest,
    ResponseSchema,
    WaitingSchema,
)
from app.database import get_db
from app.redis import get_redis, redis_execute

router = APIRouter()


@router.post("/waiting", response_model=ResponseSchema[WaitingResponse])
async def add_waiting(
    waiting_data: WaitingRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    booth_key = f"waiting:booth:{waiting_data.boothId}"
    device_key = f"waiting:device:{waiting_data.deviceId}"

    # ✅ 웨이팅 생성 후 RDB 저장
    waiting = Waiting(
        booth_id=waiting_data.boothId,
        device_id=waiting_data.deviceId,
    )
    db.add(waiting)
    await db.commit()
    await db.refresh(waiting)  
  
    async with redis_client.pipeline() as pipe:
        pipe.zadd(booth_key, {waiting.device_id: waiting.created_at.timestamp()})
        pipe.hset(
            device_key, waiting.id, WaitingSchema.from_orm(waiting).json()
        )  
        await pipe.execute()

    return ResponseSchema(
        data=WaitingResponse(
            waitingId=waiting.id,
            boothId=waiting.booth_id,
            deviceId=waiting.device_id,
            waitingOrder=None,
        )
    )


@router.get(
    "/waiting/{booth_id}/reserved", response_model=ResponseSchema[list[WaitingResponse]]
)
async def get_waiting_list(
    booth_id: int, redis_client: redis.Redis = Depends(get_redis)
):
    try:
        waiting_list = [
            device_id.decode("utf-8") if isinstance(device_id, bytes) else device_id
            for device_id in await redis_execute(
                redis_client, "zrange", f"waiting:booth:{booth_id}", 0, -1
            )
        ]

        if not waiting_list:
            return ResponseSchema(data=[])

        response_data = []
        for index, device_id in enumerate(waiting_list):
            waiting_data = await redis_execute(
                redis_client, "hgetall", f"waiting:device:{device_id}"
            )

            if not waiting_data:
                continue  

            for waiting_id, waiting_json in waiting_data.items():
                waiting_info = json.loads(waiting_json)

                if int(waiting_info["booth_id"]) == booth_id:
                    response_data.append(
                        WaitingResponse(
                            waitingId=int(waiting_id),
                            boothId=booth_id,
                            deviceId=device_id,
                            waitingOrder=index + 1,
                        )
                    )

        return ResponseSchema(data=response_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis Error: {str(e)}")


@router.get(
    "/waiting/me/{device_id}", response_model=ResponseSchema[list[WaitingResponse]]
)
async def get_my_waiting(
    device_id: str, redis_client: redis.Redis = Depends(get_redis)
):
    device_key = f"waiting:device:{device_id}"

    try:
        waiting_data = await redis_client.hgetall(device_key)
        if not waiting_data:
            return ResponseSchema(data=[])

        results = []

        for waiting_id, w_data in waiting_data.items():
            waiting_info = json.loads(w_data)
            booth_id = waiting_info["booth_id"]

            rank = await redis_client.zrank(f"waiting:booth:{booth_id}", device_id)
            waiting_order = rank + 1 if rank is not None else None

            results.append(
                WaitingResponse(
                    waitingId=int(waiting_id),
                    boothId=int(booth_id),
                    deviceId=device_id,
                    waitingOrder=waiting_order, 
                )
            )

        return ResponseSchema(data=results)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis Error: {str(e)}")


@router.get(
    "/waiting/db/{device_id}", response_model=ResponseSchema[list[WaitingResponse]]
)
async def get_my_waiting_rdb(device_id: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            select(Waiting.booth_id).where(Waiting.device_id == device_id).distinct()
        )
        booth_ids = [row[0] for row in result.fetchall()]

        if not booth_ids:
            return ResponseSchema(data=[])

        result = await db.execute(
            select(Waiting)
            .where(Waiting.booth_id.in_(booth_ids))
            .order_by(Waiting.booth_id, Waiting.created_at)
        )
        waiting_list = result.scalars().all()

        response_data = []
        for booth_id in booth_ids:
            booth_waitings = [w for w in waiting_list if w.booth_id == booth_id]
            for index, w in enumerate(booth_waitings):
                if w.device_id == device_id:
                    response_data.append(
                        WaitingResponse(
                            waitingId=w.id,
                            boothId=w.booth_id,
                            deviceId=w.device_id,
                            waitingOrder=index + 1,  # 순서는 created_at 기준
                        )
                    )

        return ResponseSchema(data=response_data)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB Error: {str(e)}")


@router.delete("/waiting/{waiting_id}", response_model=ResponseSchema[WaitingResponse])
async def remove_waiting(
    waiting_id: int,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    waiting = await db.get(Waiting, waiting_id)
    if not waiting:
        raise HTTPException(status_code=404, detail="Waiting not found")

    booth_key = f"waiting:booth:{waiting.booth_id}"
    device_key = f"waiting:device:{waiting.device_id}"

    await db.delete(waiting)
    await db.commit()

    async with redis_client.pipeline() as pipe:
        pipe.zrem(booth_key, waiting.device_id)
        pipe.hdel(device_key, waiting.id)
        await pipe.execute()

    return ResponseSchema(
        data=WaitingResponse(
            waitingId=waiting.id,
            boothId=waiting.booth_id,
            deviceId=waiting.device_id,
            waitingOrder=None,
        )
    )


@router.put("/waiting", response_model=ResponseSchema[dict])
async def cancel_waiting(
    request: CancelWaitingRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    result = await db.execute(
        Waiting.__table__.delete().where(
            Waiting.id == request.waitingId, Waiting.device_id == request.deviceId
        )
    )
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Waiting not found")

    device_key = f"waiting:device:{request.deviceId}"
    waiting_data = await redis_client.hget(device_key, request.waitingId)

    if waiting_data:
        waiting_info = json.loads(waiting_data)
        booth_id = waiting_info.get("booth_id")

        async with redis_client.pipeline() as pipe:
            pipe.zrem(f"waiting:booth:{booth_id}", request.deviceId)  # ✅ ZSET에서 삭제
            pipe.hdel(device_key, request.waitingId)  # ✅ HSET에서 삭제
            await pipe.execute()

    return ResponseSchema(data={"message": "Waiting canceled"})
