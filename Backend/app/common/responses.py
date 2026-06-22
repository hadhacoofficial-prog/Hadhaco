from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.common.response_codes import ResponseCode


class BaseSuccessResponse[T](BaseModel):
    success: bool = True
    code: str
    message: str
    data: T | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "code": "RESOURCE_FETCHED",
                    "message": "Fetched successfully",
                    "data": {},
                }
            ]
        }
    }


class BaseErrorResponse(BaseModel):
    success: bool = False
    code: str
    message: str
    data: Any = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": False,
                    "code": "NOT_FOUND",
                    "message": "Resource not found",
                    "data": None,
                }
            ]
        }
    }


def ok(data: Any, code: ResponseCode, message: str) -> BaseSuccessResponse:
    return BaseSuccessResponse(code=code.value, message=message, data=data)


def created(data: Any, code: ResponseCode, message: str) -> BaseSuccessResponse:
    return BaseSuccessResponse(code=code.value, message=message, data=data)


def deleted(code: ResponseCode, message: str) -> BaseSuccessResponse:
    return BaseSuccessResponse(code=code.value, message=message, data=None)


def accepted(data: Any, code: ResponseCode, message: str) -> BaseSuccessResponse:
    return BaseSuccessResponse(code=code.value, message=message, data=data)
