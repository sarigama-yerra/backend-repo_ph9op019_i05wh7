"""
Database Schemas for Juma Trek

Each Pydantic model maps to a MongoDB collection (lowercased class name).
- Trek -> "trek"
- BlogPost -> "blogpost"
- Inquiry -> "inquiry"
- AdminUser -> "adminuser"
"""

from typing import List, Optional
from pydantic import BaseModel, Field, EmailStr
from datetime import date

class Trek(BaseModel):
    title: str = Field(..., description="Trek title")
    slug: Optional[str] = Field(None, description="URL-friendly slug")
    region: str = Field(..., description="Geographic region")
    difficulty: str = Field(..., description="Difficulty level: Easy/Moderate/Challenging")
    duration_days: int = Field(..., ge=1, description="Total duration in days")
    price_usd: float = Field(..., ge=0, description="Starting price in USD")
    max_altitude_m: Optional[int] = Field(None, ge=0, description="Maximum altitude in meters")
    highlights: List[str] = Field(default_factory=list, description="Key highlights bullets")
    overview: str = Field(..., description="Short overview")
    itinerary: List[str] = Field(default_factory=list, description="Day-wise itinerary")
    inclusions: List[str] = Field(default_factory=list)
    exclusions: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list, description="Image URLs")
    is_featured: bool = Field(False, description="Show on homepage")

class BlogPost(BaseModel):
    title: str
    slug: Optional[str] = None
    excerpt: Optional[str] = None
    content: str
    cover_image: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    published: bool = True
    published_on: Optional[date] = None

class Inquiry(BaseModel):
    name: str
    email: EmailStr
    trek_id: Optional[str] = Field(None, description="Optional trek id of interest")
    subject: Optional[str] = None
    message: str
    preferred_start_date: Optional[date] = None
    travelers: Optional[int] = Field(default=1, ge=1)

class AdminUser(BaseModel):
    email: EmailStr
    password_hash: str
    password_salt: str
    full_name: Optional[str] = None
    role: str = Field(default="admin")
