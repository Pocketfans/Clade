import secrets
from typing import Literal

from fastapi import Depends, Header, HTTPException, Request

from app.core.config import Settings, get_settings


class AdminTokenValidationError(Exception):
    def __init__(
        self,
        code: Literal["admin_token_unconfigured", "admin_token_invalid"],
        status_code: Literal[403, 503],
        public_message: str,
    ) -> None:
        super().__init__(public_message)
        self.code = code
        self.status_code = status_code
        self.public_message = public_message


def validate_admin_token(
    provided_token: str | None,
    configured_token: str | None,
) -> None:
    if not configured_token:
        raise AdminTokenValidationError(
            "admin_token_unconfigured", 503, "管理员功能未启用"
        )

    if not secrets.compare_digest(
        (provided_token or "").encode("utf-8"),
        configured_token.encode("utf-8"),
    ):
        raise AdminTokenValidationError(
            "admin_token_invalid", 403, "管理员令牌无效"
        )


def require_admin_token(
    request: Request,
    x_clade_admin_token: str | None = Header(
        default=None, alias="X-Clade-Admin-Token"
    ),
    settings: Settings = Depends(get_settings),
) -> None:
    if request.method in {"GET", "HEAD"}:
        return

    try:
        validate_admin_token(x_clade_admin_token, settings.clade_admin_token)
    except AdminTokenValidationError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.public_message,
        ) from None
