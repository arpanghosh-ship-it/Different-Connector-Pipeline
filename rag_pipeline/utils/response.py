"""
response.py
Standardized API response envelope used by all endpoints.

Every endpoint returns:
{
    "success": bool,
    "message": str,
    "data":    dict
}
"""

from fastapi.responses import JSONResponse
from typing import Any


def success_response(
    message: str,
    data: Any = None,
    status_code: int = 200
) -> JSONResponse:
    """
    Return a standardized success response.

    Args:
        message:     Human-readable success message
        data:        The actual response payload (dict, list, or None)
        status_code: HTTP status code (default 200)
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "message": message,
            "data":    data if data is not None else {}
        }
    )


def error_response(
    message: str,
    data: Any = None,
    status_code: int = 400
) -> JSONResponse:
    """
    Return a standardized error response.

    Args:
        message:     Human-readable error message explaining what failed
        data:        Optional error details (dict or None)
        status_code: HTTP status code (default 400)
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "message": message,
            "data":    data if data is not None else {}
        }
    )
