from datetime import datetime
from typing import Optional, TypeVar, Generic
from pydantic import BaseModel

T = TypeVar("T")


class ResponseSchema(BaseModel, Generic[T]):
    data: T


class WaitingRequest(BaseModel):
    boothId: int
    deviceId: str
    pinNumber: str
    tel: str
    partySize: int


class CancelWaitingRequest(BaseModel):
    waitingId: int
    deviceId: str


class WaitingResponse(BaseModel):
    waitingId: int
    boothId: int
    deviceId: str
    waitingOrder: Optional[int]


class WaitingSchema(BaseModel):
    id: int
    booth_id: int
    device_id: str
    created_at: datetime

    class Config:
        orm_mode = True
