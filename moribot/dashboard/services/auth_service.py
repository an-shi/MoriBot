"""Authentication service for dashboard accounts."""

from __future__ import annotations

from loguru import logger

from moribot.core.accounts import delete_initial_credentials
from moribot.core.config import ConfigManager
from moribot.core.db import BaseDatabase, User, utcnow
from moribot.core.errors import (
    AuthenticationError,
    MoriError,
    NotFoundError,
    PermissionDeniedError,
)
from moribot.core.i18n import translate
from moribot.core.paths import AppPaths
from moribot.core.security import (
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)

from ..schemas import TokenData, UserOut

# A real hash keeps the "unknown user" branch roughly as expensive as the
# "wrong password" branch, avoiding a trivial account-enumeration oracle.
_DUMMY_PASSWORD_HASH = hash_password("moribot-timing-guard")


class AuthService:
    """Credential verification and token issuing."""

    def __init__(
        self,
        db: BaseDatabase,
        config: ConfigManager,
        paths: AppPaths | None = None,
    ) -> None:
        self.db = db
        self.config = config
        self.paths = paths

    async def login(self, username: str, password: str, locale: str | None = None) -> TokenData:
        """Authenticate a username/password pair and issue a token.

        Args:
            username: Account name.
            password: Plaintext password.
            locale: Language used for error messages.

        Returns:
            Token payload including the public user record.

        Raises:
            AuthenticationError: For unknown, inactive or mismatched accounts.
        """
        locale = locale or self.config.locale
        user = await self.db.get_user_by_username(username.strip())
        if user is None:
            verify_password(_DUMMY_PASSWORD_HASH, password)
            raise AuthenticationError(translate("auth.invalid_credentials", locale))
        if not verify_password(user.password_hash, password):
            raise AuthenticationError(translate("auth.invalid_credentials", locale))
        if not user.is_active:
            raise PermissionDeniedError(translate("auth.account_disabled", locale))

        await self.db.record_login(user.id)
        user.last_login_at = utcnow()
        return self._issue_token(user)

    async def change_password(
        self,
        user: User,
        *,
        current_password: str,
        new_password: str,
        confirm_password: str,
        locale: str | None = None,
    ) -> TokenData:
        """Change a password and revoke every previously issued token.

        Args:
            user: Currently authenticated account.
            current_password: Existing password for confirmation.
            new_password: New password.
            confirm_password: Repeated new password.
            locale: Language used for validation messages.

        Returns:
            A fresh token for the updated account.

        Raises:
            MoriError: When validation or the current password check fails.
        """
        locale = locale or self.config.locale
        if new_password != confirm_password:
            raise MoriError(translate("auth.password_mismatch", locale))
        if not verify_password(user.password_hash, current_password):
            raise MoriError(translate("auth.current_password_incorrect", locale))
        if current_password == new_password:
            raise MoriError(translate("auth.new_password_same", locale))

        try:
            validate_password_strength(new_password, locale=locale)
        except ValueError as exc:
            raise MoriError(str(exc)) from exc

        updated = await self.db.update_user_password(user.id, hash_password(new_password))
        if updated is None:
            raise NotFoundError(translate("auth.account_missing", locale))

        if self.paths is not None:
            delete_initial_credentials(self.paths)
        logger.info("Password changed for account {}.", updated.username)
        return self._issue_token(updated)

    def _issue_token(self, user: User) -> TokenData:
        if user.id is None:
            raise MoriError(
                translate("auth.account_data_error", self.config.locale),
                status_code=500,
            )

        token, expires_in = create_access_token(
            secret=self.config.jwt_secret,
            user_id=user.id,
            username=user.username,
            role=user.role,
            token_version=user.token_version,
            expires_hours=self.config.token_expire_hours,
        )
        return TokenData(
            access_token=token,
            expires_in=expires_in,
            user=UserOut.model_validate(user),
        )
