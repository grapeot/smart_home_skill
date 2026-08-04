import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException, status


CONTROL_TOKEN_ENV = "SMART_HOME_API_TOKEN"
GARAGE_BRIDGE_TOKEN_ENV = "GARAGE_BRIDGE_TOKEN"


def require_control_auth(
    x_smart_home_token: Optional[str] = Header(default=None, alias="X-Smart-Home-Token"),
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Require an API token for physical actions when configured."""
    expected = os.getenv(CONTROL_TOKEN_ENV)
    if not expected:
        return

    provided = x_smart_home_token
    if not provided and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            provided = value

    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid smart home control token required",
        )


def require_garage_bridge_auth(
    x_garage_bridge_token: Optional[str] = Header(
        default=None, alias="X-Garage-Bridge-Token"
    ),
    authorization: Optional[str] = Header(default=None),
) -> None:
    """Fail closed for the dedicated ESP-NOW bridge ingress."""
    expected = os.getenv(GARAGE_BRIDGE_TOKEN_ENV)
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Garage bridge authentication is not configured",
        )

    provided = x_garage_bridge_token
    if not provided and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            provided = value

    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Valid garage bridge token required",
        )
