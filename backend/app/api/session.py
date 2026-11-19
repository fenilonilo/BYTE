from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_master
from app.api.deps import get_device_auth
from app.api.schemas import RefreshSchema, TokenPairSchema
from app.application.device_auth import DeviceAuth, TokenPair

router = APIRouter(prefix="/auth")
Auth = Annotated[DeviceAuth, Depends(get_device_auth)]


def _schema(pair: TokenPair) -> TokenPairSchema:
    return TokenPairSchema(
        access_token=pair.access, refresh_token=pair.refresh, expires_in=pair.expires_in
    )


@router.post("/login", response_model=TokenPairSchema, dependencies=[Depends(require_master)])
async def login(auth: Auth) -> TokenPairSchema:
    """Sign this device in with the master token, once."""
    return _schema(await auth.login())


@router.post("/refresh", response_model=TokenPairSchema)
async def refresh(body: RefreshSchema, auth: Auth) -> TokenPairSchema:
    pair = await auth.refresh(body.refresh_token)
    if pair is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in again")
    return _schema(pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshSchema, auth: Auth) -> None:
    await auth.logout(body.refresh_token)
