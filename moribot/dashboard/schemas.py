"""Request and response schemas for the dashboard API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)
    confirm_password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: str
    last_login_at: datetime | None = None


class TokenData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class PublicInfo(BaseModel):
    name: str
    version: str
    description: str = ""


class SystemInfo(BaseModel):
    name: str
    version: str
    running: bool
    started_at: str | None = None
    uptime_seconds: int = 0
    providers: int = 0
    platforms: int = 0
    plugins: int = 0
    mobile_online: int = 0
    python_version: str = ""


class HealthInfo(BaseModel):
    status: str = "ok"
    version: str


class MobilePairRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    device_name: str = Field(min_length=1, max_length=64)


class MobileSendRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8000)


class PairingCodeOut(BaseModel):
    code: str
    expires_at: datetime
    pairing_uri: str
    server_url: str = ""


class MobileDeviceOut(BaseModel):
    id: str
    name: str
    online: bool = False
    created_at: datetime
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None


class MobilePairOut(BaseModel):
    device_token: str
    device: MobileDeviceOut
