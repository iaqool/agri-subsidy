import re
from pydantic import BaseModel, field_validator
from typing import Optional, Dict

_B58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


class FarmerRegistration(BaseModel):
    wallet_address: str
    region_lat: float
    region_lon: float

    @field_validator("wallet_address")
    @classmethod
    def validate_wallet(cls, v: str) -> str:
        v = v.strip()
        if not _B58_RE.match(v):
            raise ValueError("Invalid Solana wallet address")
        return v

    @field_validator("region_lat")
    @classmethod
    def validate_lat(cls, v: float) -> float:
        if not -90 <= v <= 90:
            raise ValueError("Latitude must be between -90 and 90")
        return v

    @field_validator("region_lon")
    @classmethod
    def validate_lon(cls, v: float) -> float:
        if not -180 <= v <= 180:
            raise ValueError("Longitude must be between -180 and 180")
        return v


class EvaluationResult(BaseModel):
    approved: bool
    score: int
    reasoning: str
    is_fallback: bool = False

class AILogEntry(BaseModel):
    step: str
    content: str

class FarmerStatus(BaseModel):
    wallet: str
    lat: float
    lon: float
    status: str  # "pending", "approved", "rejected"
    score: Optional[int] = None
    tx_signature: Optional[str] = None
