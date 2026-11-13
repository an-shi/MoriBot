"""Request and response schemas for the dashboard API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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


class HealthCheckSettings(BaseModel):
    enabled: bool = True
    times: list[str] = Field(default_factory=list)
    last_runs: dict[str, str] = Field(default_factory=dict)


class SystemSettingsOut(BaseModel):
    health_check: HealthCheckSettings
    server_time: str = ""
    timezone: str = ""


class HealthCheckSettingsUpdate(BaseModel):
    enabled: bool
    times: list[str] = Field(default_factory=list)


class SystemSettingsUpdate(BaseModel):
    health_check: HealthCheckSettingsUpdate


class ModelHealthRunOut(BaseModel):
    checked: int = 0
    available: int = 0
    failed: int = 0


class LogEntryOut(BaseModel):
    time: float
    level: str
    source: str = "app"
    message: str
    module: str = ""
    line: int = 0


class SystemLogsOut(BaseModel):
    entries: list[LogEntryOut] = Field(default_factory=list)
    total: int = 0


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


class MobileSelfOut(BaseModel):
    device: MobileDeviceOut
    user: UserOut
    server_version: str
    protocol: int


class MobileCharacterOut(BaseModel):
    """A character card as seen by the phone.

    The long persona prompt stays on the server; the phone only needs enough
    metadata to render a picker and know which media capabilities are usable.
    """

    id: int
    name: str
    avatar: str = ""
    description: str = ""
    chat_available: bool = True
    speech_available: bool = False
    image_available: bool = False
    updated_at: datetime


class MobileChatMessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class MobileChatRequest(BaseModel):
    """One conversation turn.

    The phone owns the history and sends the full context on every request.
    ``client_message_id`` is echoed back so the client can match the reply to
    the local message that triggered it.
    """

    character_id: int
    messages: list[MobileChatMessageIn] = Field(min_length=1, max_length=200)
    client_message_id: str = Field(default="", max_length=128)
    speech: bool = False


class MobileChatModelOut(BaseModel):
    provider_id: str
    model: str


class MobileSpeechOut(BaseModel):
    mime_type: str = "audio/mpeg"
    format: str = "mp3"
    data_url: str
    byte_length: int = 0


class MobileImageOut(BaseModel):
    mime_type: str = "image/png"
    data_url: str | None = None
    url: str | None = None


class MobileChatOut(BaseModel):
    client_message_id: str
    character_id: int
    text: str = ""
    speech: MobileSpeechOut | None = None
    images: list[MobileImageOut] = Field(default_factory=list)
    chat_model: MobileChatModelOut
    created_at: datetime


ProviderCategoryLiteral = Literal["chat", "speech", "image"]


class ProviderTypeOut(BaseModel):
    id: str
    name: str
    description: str
    categories: list[ProviderCategoryLiteral]
    default_base_url: str = ""
    api_key_required: bool = True
    docs_url: str = ""


class ProviderPresetOut(BaseModel):
    id: str
    name: str
    provider_type: str
    categories: list[ProviderCategoryLiteral]
    base_url: str = ""
    models: dict[str, list[str]] = Field(default_factory=dict)
    docs_url: str = ""
    api_key_required: bool = True
    voice: str = ""


class ProviderCatalogOut(BaseModel):
    types: list[ProviderTypeOut] = Field(default_factory=list)
    presets: list[ProviderPresetOut] = Field(default_factory=list)


class ProviderCreateRequest(BaseModel):
    category: ProviderCategoryLiteral
    name: str = Field(min_length=1, max_length=64)
    provider_type: str = "openai_compatible"
    base_url: str = Field(min_length=1, max_length=512)
    api_key: str = Field(default="", max_length=2048)
    model: str = Field(min_length=1, max_length=128)
    options: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False
    enabled: bool = True


class ProviderUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    provider_type: str | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=512)
    api_key: str | None = Field(default=None, max_length=2048)
    model: str | None = Field(default=None, min_length=1, max_length=128)
    options: dict[str, Any] | None = None
    capabilities: dict[str, Any] | None = None
    is_default: bool | None = None
    enabled: bool | None = None


class ProviderModelsRequest(BaseModel):
    provider_type: str
    category: ProviderCategoryLiteral
    base_url: str = Field(min_length=1, max_length=512)
    api_key: str = Field(default="", max_length=2048)
    provider_id: int | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ProviderModelInfo(BaseModel):
    id: str
    name: str
    capabilities: dict[str, Any] = Field(default_factory=dict)
    owned_by: str = ""


class ProviderModelsOut(BaseModel):
    models: list[ProviderModelInfo] = Field(default_factory=list)
    message: str = ""
    manual_allowed: bool = True


class ProviderOut(BaseModel):
    id: int
    category: ProviderCategoryLiteral
    name: str
    provider_type: str
    base_url: str
    model: str
    options: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = False
    enabled: bool = True
    api_key_set: bool = False
    api_key_hint: str = ""
    last_test_ok: bool | None = None
    last_test_message: str = ""
    last_tested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProviderTestResult(BaseModel):
    ok: bool
    message: str
    latency_ms: int = 0
    preview: str = ""


class CharacterCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    avatar: str = Field(default="", max_length=512)
    description: str = Field(default="", max_length=1000)
    persona: str = Field(default="", max_length=20000)
    chat_provider_id: int | None = None
    speech_provider_id: int | None = None
    image_provider_id: int | None = None
    enabled: bool = True


class CharacterUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    avatar: str | None = Field(default=None, max_length=512)
    description: str | None = Field(default=None, max_length=1000)
    persona: str | None = Field(default=None, max_length=20000)
    chat_provider_id: int | None = None
    speech_provider_id: int | None = None
    image_provider_id: int | None = None
    enabled: bool | None = None


class CharacterOut(BaseModel):
    id: int
    name: str
    avatar: str = ""
    description: str = ""
    persona: str = ""
    chat_provider_id: int | None = None
    speech_provider_id: int | None = None
    image_provider_id: int | None = None
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class CharacterAvatarUploadRequest(BaseModel):
    data_url: str = Field(min_length=1, max_length=4_000_000)


class CharacterAvatarOut(BaseModel):
    url: str
