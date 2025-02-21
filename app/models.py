from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, func
from sqlalchemy.orm import relationship


from app.database import Base


class Booth(Base):
    __tablename__ = "booths"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)


class Waiting(Base):
    __tablename__ = "waiting"
    id = Column(Integer, primary_key=True, index=True)
    booth_id = Column(Integer, ForeignKey("booths.id"), nullable=False)
    device_id = Column(String, nullable=False, index=True)
    status = Column(String, default="RESERVED")
    created_at = Column(DateTime, default=func.now())

    booth = relationship("Booth")
