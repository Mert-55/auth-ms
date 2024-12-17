"""Endpoints for user management"""

import hashlib
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from pyotp import random_base32
from sqlalchemy import asc, func, or_

from .. import models
from ..auth import admin_auth, get_user, is_admin, user_auth
from ..database import db, filter_by, select
from ..exceptions.auth import PermissionDeniedError, admin_responses, user_responses
from ..exceptions.user import (
    EmailAlreadyExistsError,
    EmailAlreadyVerifiedError,
    InvalidEmailError,
    InvalidVerificationCodeError,
    NoLoginMethodError,
    PasswordResetFailedError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from ..utils.docs import responses
from ..redis_client import redis
from ..schemas.session import LoginResponse
from ..schemas.user import (
    VERIFICATION_CODE_REGEX,
    CreateUser,
    RequestPasswordReset,
    ResetPassword,
    UpdateUser,
    User,
    UsersResponse,
)
from ..settings import settings
from ..utils.email import check_email_deliverability
from ..utils.utc import utcnow


router = APIRouter()


@router.get(
    "/users", dependencies=[admin_auth], responses=admin_responses(UsersResponse)
)
async def get_users(
    limit: int = Query(
        100, ge=1, le=100, description="The maximum number of users to return"
    ),
    offset: int = Query(
        0, ge=0, description="The number of users to skip for pagination"
    ),
    name: str | None = Query(
        None,
        max_length=256,
        description="A search term to match against the user's name",
    ),
    email: str | None = Query(
        None,
        max_length=256,
        description="A search term to match against the user's email",
    ),
    enabled: bool | None = Query(
        None, description="Return only users with the given enabled status"
    ),
    admin: bool | None = Query(
        None, description="Return only users with the given admin status"
    ),
    email_verified: bool | None = Query(
        None, description="Return only users with the given email verification status"
    ),
) -> Any:
    """
    Return a list of all users matching the given criteria.

    *Requirements:* **ADMIN**
    """

    query = select(models.User)
    order = []
    if name:
        query = query.where(
            or_(
                func.lower(models.User.name).contains(name.lower(), autoescape=True),
                func.lower(models.User.display_name).contains(
                    name.lower(), autoescape=True
                ),
            )
        )
        order.append(asc(func.length(models.User.name)))
    if email:
        query = query.where(
            func.lower(models.User.email).contains(email.lower(), autoescape=True)
        )
        order.append(asc(func.length(models.User.email)))
    if enabled is not None:
        query = query.where(models.User.enabled == enabled)
    if admin is not None:
        query = query.where(models.User.admin == admin)
    if email_verified is True:
        query = query.where(models.User.email_verification_code == None)  # noqa
    elif email_verified is False:
        query = query.where(models.User.email_verification_code != None)  # noqa

    return {
        "total": await db.count(query),
        "users": [
            user.serialize
            async for user in await db.stream(
                query.order_by(*order, asc(models.User.registration))
                .limit(limit)
                .offset(offset)
            )
        ],
    }


@router.get("/users/{user_id}", responses=admin_responses(User, UserNotFoundError))
async def get_user_by_id(
    user: models.User = get_user(require_self_or_admin=True),
) -> Any:
    """
    Return a user by ID.

    *Requirements:* **SELF** or **ADMIN**
    """

    return user.serialize


@router.post(
    "/users",
    responses=user_responses(
        LoginResponse,
        UserAlreadyExistsError,
        EmailAlreadyExistsError,
        NoLoginMethodError,
        RegistrationDisabledError,
        InvalidEmailError,
    ),
)
async def create_user(
    data: CreateUser, request: Request, admin: bool = is_admin
) -> Any:
    """
    Create a new user and a new session for them.

    If the **ADMIN** requirement is *not* met:
    - The user is always created as a regular user (`"enabled": true, "admin": false`).
    - A recaptcha response is required if recaptcha is enabled (see `GET /recaptcha`).

    The value of the `User-agent` header is used as the device name of the created session.
    """

    if not data.password:
        raise NoLoginMethodError
    if not admin:
        if data.password and not settings.open_registration:
            raise RegistrationDisabledError

        if not await check_email_deliverability(data.email):
            raise InvalidEmailError

    if await db.exists(models.User.filter_by_name(data.name)):
        raise UserAlreadyExistsError
    if await db.exists(models.User.filter_by_email(data.email)):
        raise EmailAlreadyExistsError

    user = await models.User.create(
        data.name,
        data.display_name,
        data.email,
        data.password,
        data.enabled or not admin,
        data.admin and admin,
    )

    session, access_token, refresh_token = await user.create_session(
        request.headers.get("User-agent", "")[:256]
    )
    return {
        "user": user.serialize,
        "session": session.serialize,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@router.patch(
    "/users/{user_id}",
    responses=admin_responses(
        User,
        UserNotFoundError,
        UserAlreadyExistsError,
        EmailAlreadyExistsError,
        InvalidEmailError,
    ),
)
async def update_user(
    data: UpdateUser,
    user: models.User = get_user(models.User.sessions, require_self_or_admin=True),
    admin: bool = is_admin,
    session: models.Session = user_auth,
) -> Any:
    """
    Update an existing user.

    - Changing the email address will also set it to unverified.
    - Setting `password` to `null` or omitting it will not change the user's password while setting it to
      the empty string will remove the user's password.
    - Disabling a user will also log them out.
    - A user can never change their own admin status.

    *Requirements:* **SELF** or **ADMIN**

    If the **ADMIN** requirement is *not* met:
    - The username cannot be changed.
    - The user cannot be enabled or disabled.
    - The email verification status cannot be changed.
    - The admin status cannot be changed.
    """

    if data.name is not None and data.name != user.name:
        now = utcnow()
        if not admin and now - user.last_name_change < timedelta(
            days=settings.min_name_change_interval
        ):
            raise PermissionDeniedError
        if await db.exists(
            models.User.filter_by_name(data.name).where(models.User.id != user.id)
        ):
            raise UserAlreadyExistsError

        user.name = data.name
        if not admin:
            user.last_name_change = now

    if data.display_name is not None and data.display_name != user.display_name:
        user.display_name = data.display_name

    if data.email is not None and data.email != user.email:
        if await db.exists(
            models.User.filter_by_email(data.email).where(models.User.id != user.id)
        ):
            raise EmailAlreadyExistsError
        if not admin and not await check_email_deliverability(data.email):
            raise InvalidEmailError

        user.email = data.email
        user.email_verified = False
        await user.invalidate_access_tokens()

    if data.email_verified is not None and data.email_verified != user.email_verified:
        if not admin:
            raise PermissionDeniedError

        user.email_verified = data.email_verified
        await user.invalidate_access_tokens()

    if data.password is not None:
        await user.change_password(data.password)

    if data.enabled is not None and data.enabled != user.enabled:
        if user.id == session.user_id:
            raise PermissionDeniedError

        user.enabled = data.enabled
        if not user.enabled:
            await user.logout()

    if data.admin is not None and data.admin != user.admin:
        if user.id == session.user_id:
            raise PermissionDeniedError

        user.admin = data.admin
        await user.invalidate_access_tokens()

    if data.description is not None and data.description != user.description:
        user.description = data.description

    if data.tags is not None and data.tags != user.tags:
        user.tags = data.tags

    if data.first_name is not None and data.first_name != user.first_name:
        user.first_name = data.first_name

    if data.last_name is not None and data.last_name != user.last_name:
        user.last_name = data.last_name

    if data.street is not None and data.street != user.street:
        user.street = data.street

    if data.zip_code is not None and data.zip_code != user.zip_code:
        user.zip_code = data.zip_code

    if data.city is not None and data.city != user.city:
        user.city = data.city

    if data.country is not None and data.country != user.country:
        user.country = data.country

    return user.serialize


@router.post(
    "/users/{user_id}/email",
    responses=admin_responses(
        bool, UserNotFoundError, EmailAlreadyVerifiedError, InvalidEmailError
    ),
)
async def request_verification_email(
    user: models.User = get_user(require_self_or_admin=True),
) -> Any:
    """
    Request a verification email.

    This will send an email to the user's email address with a code for the `PUT /users/me/email` endpoint to
    verify their email address.

    *Requirements:* **SELF** or **ADMIN**
    """

    if user.email_verified:
        raise EmailAlreadyVerifiedError

    try:
        await user.send_verification_email()
    except ValueError:
        raise InvalidEmailError
    return True


@router.put(
    "/users/me/email", responses=admin_responses(bool, InvalidVerificationCodeError)
)
async def verify_email(
    code: str = Body(
        embed=True,
        regex=VERIFICATION_CODE_REGEX,
        description="The code from the verification email",
    )
) -> Any:
    """
    Verify a user's email address.

    To request a verification email, use the `POST /users/{user_id}/email` endpoint.

    *Requirements:* **SELF** or **ADMIN**
    """

    user: models.User | None = await db.first(
        models.User.filter_by_verification_code(code, models.User.sessions)
    )
    if not user:
        raise InvalidVerificationCodeError

    user.email_verified = True
    await user.invalidate_access_tokens()
    return True


@router.delete("/users/{user_id}", responses=admin_responses(bool, UserNotFoundError))
async def delete_user(
    user: models.User = get_user(models.User.sessions, require_self_or_admin=True),
    admin: bool = is_admin,
) -> Any:
    """
    Delete a user.

    If only one admin exists, this user cannot be deleted.

    *Requirements:* **SELF** or **ADMIN**
    """

    if not (settings.open_registration) and not admin:
        raise PermissionDeniedError

    if user.admin and not await db.exists(
        filter_by(models.User, admin=True).filter(models.User.id != user.id)
    ):
        raise PermissionDeniedError

    await user.logout()
    await db.delete(user)
    return True


@router.post("/password_reset", responses=responses(bool, InvalidEmailError))
async def request_password_reset(data: RequestPasswordReset) -> Any:
    """
    Request a password reset email.

    This will send an email to the user's email address with a code for the `PUT /password_reset` endpoint to
    reset their password. This code expires after one hour.
    """

    if user := await db.first(models.User.filter_by_email(data.email)):
        try:
            await user.send_password_reset_email()
        except ValueError:
            raise InvalidEmailError

    return True


@router.put("/password_reset", responses=responses(User, PasswordResetFailedError))
async def reset_password(data: ResetPassword) -> Any:
    """
    Reset a user's password.

    To request a password reset email, use the `POST /password_reset` endpoint.

    *Requirements:* **SELF** or **ADMIN**
    """

    user: models.User | None = await db.first(models.User.filter_by_email(data.email))
    if not user:
        raise PasswordResetFailedError

    if not await user.check_password_reset_code(data.code):
        raise PasswordResetFailedError

    await user.change_password(data.password)
    return user.serialize
