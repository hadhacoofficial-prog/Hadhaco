import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_VALID_STATUSES = (
    "new_enquiry",
    "contacted_customer",
    "positive_response",
    "negative_response",
    "closed",
)
_STATUS_PATTERN = (
    "^(new_enquiry|contacted_customer|positive_response|negative_response|closed)$"
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(v: str) -> str:
    return _HTML_TAG_RE.sub("", v).strip()


class EnquiryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=255)
    phone: str | None = Field(None, max_length=50)
    subject: str = Field(..., min_length=1, max_length=500)
    message: str = Field(..., min_length=1, max_length=5000)
    website: str = Field(default="", max_length=500)

    @field_validator("name", "subject")
    @classmethod
    def sanitize_html(cls, v: str) -> str:
        return _strip_html(v)

    @field_validator("message")
    @classmethod
    def sanitize_message(cls, v: str) -> str:
        return _strip_html(v)


class EnquiryUpdateRequest(BaseModel):
    status: str | None = Field(None, pattern=_STATUS_PATTERN)
    admin_notes: str | None = None


class EnquiryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    name: str
    email: str
    phone: str | None
    subject: str
    message: str
    status: str
    admin_notes: str | None
    contacted_at: datetime | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EnquiryStats(BaseModel):
    total: int
    new_enquiry: int
    contacted_customer: int
    positive_response: int
    negative_response: int
    closed: int
    archived: int


class EnquiryPage(BaseModel):
    items: list[EnquiryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: EnquiryStats
