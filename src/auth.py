from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader

from .config import get_settings

x_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

settings = get_settings()


def verify_api_key(api_key: str = Depends(x_api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid X-API-key Header")
    return api_key
