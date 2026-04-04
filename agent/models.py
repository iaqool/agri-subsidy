from pydantic import BaseModel
from typing import Optional, Dict

class FarmerRegistration(BaseModel):
    wallet_address: str
    region_lat: float
    region_lon: float

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
    status: str # "pending", "approved", "rejected"
    score: Optional[int] = None
    tx_signature: Optional[str] = None
