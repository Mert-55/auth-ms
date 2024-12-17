"""Endpoints for session management"""

from typing import Any

from fastapi import APIRouter, Body, Request

from .. import models
from ..auth import admin_auth, get_user, user_auth
from ..database import db, filter_by
from ..exceptions.auth import admin_responses, user_responses
from ..exceptions.session import (
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    SessionNotFoundError,
    UserDisabledError,
)
from ..exceptions.user import UserNotFoundError
from ..models.session import SessionExpiredError
from ..schemas.session import Login, LoginResponse, Session
from ..utils.docs import responses


router = APIRouter()


@router.get("/session", responses=user_responses(Session))
async def get_current_session(session: models.Session = user_auth) -> Any:
    """
    Return the current session.

    *Requirements:* **USER**
    """

    return session.serialize


@router.get(
    "/sessions/{user_id}", responses=admin_responses(list[Session], UserNotFoundError)
)
async def get_sessions(user: models.User = get_user(require_self_or_admin=True)) -> Any:
    """
    Return all sessions of a user.

    *Requirements:* **SELF** or **ADMIN**
    """

    return [
        session.serialize
        async for session in await db.stream(filter_by(models.Session, user_id=user.id))
    ]


@router.post(
    "/sessions",
    responses=responses(LoginResponse, InvalidCredentialsError, UserDisabledError),
)
async def login(data: Login, request: Request) -> Any:
    """
    Create a new session via username/password authentication.

    The client should use the following procedure to login:
    1. Try to login with name/email and password only.
    2. If a `RecaptchaError` is raised, ask the user to solve the captcha (get the recaptcha sitekey from
       `GET /recaptcha`) and repeat the request with the obtained recaptcha response. Go back to step 2.
    3. If a `InvalidCredentialsError` is raised, try again with a different username or password. Go back to step 2.
    4. If a `InvalidCodeError` is raised, MFA is enabled. Try again with the current MFA code or a recovery code.
       Go back to step 2.
    5. If a `UserDisabledError` is raised, the user is disabled and a session cannot be created.
    6. If the request was successful, the response contains an access token and a refresh token for authentication.

    The value of the `User-agent` header is used as the device name of the created session.
    """

    user: models.User | None = await db.first(
        models.User.login_filter(data.name_or_email)
    )
    if not user or not await user.check_password(data.password):
        raise InvalidCredentialsError

    if not user.enabled:
        raise UserDisabledError

    session, access_token, refresh_token = await user.create_session(
        request.headers.get("User-agent", "")[:256]
    )
    return {
        "user": user.serialize,
        "session": session.serialize,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@router.post(
    "/sessions/{user_id}",
    dependencies=[admin_auth],
    responses=admin_responses(LoginResponse, UserNotFoundError),
)
async def impersonate(request: Request, user: models.User = get_user()) -> Any:
    """
    Impersonate a specific user by creating a new session for them.

    *Requirements:* **ADMIN**
    """

    session, access_token, refresh_token = await user.create_session(
        request.headers.get("User-agent", "")[:256]
    )
    return {
        "user": user.serialize,
        "session": session.serialize,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@router.put("/session", responses=responses(LoginResponse, InvalidRefreshTokenError))
async def refresh(
    refresh_token: str = Body(
        embed=True, description="The refresh token of an existing session"
    )
) -> Any:
    """
    Refresh access token and refresh token of an existing session.

    *Note:* The old refresh token is invalidated. To refresh the session again later, use the new refresh token that is
    returned by this endpoint.
    """

    try:
        session, access_token, refresh_token = await models.Session.refresh(
            refresh_token
        )
    except (ValueError, SessionExpiredError):
        raise InvalidRefreshTokenError

    return {
        "user": session.user.serialize,
        "session": session.serialize,
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


@router.delete("/session", responses=user_responses(bool))
async def logout_current_session(session: models.Session = user_auth) -> Any:
    """
    Delete the current session.

    *Requirements:* **USER**
    """

    await session.logout()
    return True


@router.delete(
    "/sessions/{user_id}", responses=admin_responses(bool, UserNotFoundError)
)
async def logout(
    user: models.User = get_user(models.User.sessions, require_self_or_admin=True)
) -> Any:
    """
    Delete all sessions of a given user.

    *Requirements:* **SELF** or **ADMIN**
    """

    await user.logout()
    return True


@router.delete(
    "/sessions/{user_id}/{session_id}",
    responses=admin_responses(bool, UserNotFoundError, SessionNotFoundError),
)
async def logout_session(
    session_id: str, user: models.User = get_user(require_self_or_admin=True)
) -> Any:
    """
    Delete a specific session of a given user.

    *Requirements:* **SELF** or **ADMIN**
    """

    session: models.Session | None = await db.get(
        models.Session, id=session_id, user_id=user.id
    )
    if not session:
        raise SessionNotFoundError

    await session.logout()
    return True
