"""Business logic helpers for user management operations."""

from datetime import timedelta

from .. import models
from ..database import db
from ..exceptions.auth import PermissionDeniedError
from ..exceptions.user import (
    EmailAlreadyExistsError,
    InvalidEmailError,
    UserAlreadyExistsError,
)
from ..settings import settings
from ..utils.email import check_email_deliverability
from ..utils.utc import utcnow


async def validate_name_change(
    user: models.User, new_name: str, is_admin: bool
) -> None:
    """Validate name change respecting cooldown and uniqueness.
    
    Args:
        user: User model instance being updated
        new_name: The new name to validate
        is_admin: Whether the requester is an admin
        
    Raises:
        PermissionDeniedError: If non-admin tries to change before cooldown
        UserAlreadyExistsError: If the new name is already taken
    """
    now = utcnow()
    if not is_admin and now - user.last_name_change < timedelta(
        days=settings.min_name_change_interval
    ):
        raise PermissionDeniedError
    
    if await db.exists(
        models.User.filter_by_name(new_name).where(models.User.id != user.id)
    ):
        raise UserAlreadyExistsError


async def apply_name_change(
    user: models.User, new_name: str, is_admin: bool
) -> None:
    """Apply validated name change to user.
    
    Args:
        user: User model instance to update
        new_name: The new name to set
        is_admin: Whether the requester is an admin
    """
    user.name = new_name
    if not is_admin:
        user.last_name_change = utcnow()


async def validate_email_change(
    user: models.User, new_email: str, is_admin: bool
) -> None:
    """Validate email change for uniqueness and deliverability.
    
    Args:
        user: User model instance being updated
        new_email: The new email to validate
        is_admin: Whether the requester is an admin
        
    Raises:
        EmailAlreadyExistsError: If the email is already in use
        InvalidEmailError: If non-admin uses invalid/undeliverable email
    """
    if await db.exists(
        models.User.filter_by_email(new_email).where(models.User.id != user.id)
    ):
        raise EmailAlreadyExistsError
    
    if not is_admin and not await check_email_deliverability(new_email):
        raise InvalidEmailError


async def apply_email_change(user: models.User, new_email: str) -> None:
    """Apply validated email change and reset verification.
    
    Args:
        user: User model instance to update
        new_email: The new email to set
    """
    user.email = new_email
    user.email_verified = False
    await user.invalidate_access_tokens()


async def apply_password_change(user: models.User, new_password: str) -> None:
    """Apply password change to user.
    
    Args:
        user: User model instance to update
        new_password: The new password to set
    """
    await user.change_password(new_password)


async def validate_enable_change(
    user: models.User, session: models.Session
) -> None:
    """Validate that user can be enabled/disabled.
    
    Args:
        user: User model instance being updated
        session: Current session (to check if self-modification)
        
    Raises:
        PermissionDeniedError: If user tries to disable themselves
    """
    if user.id == session.user_id:
        raise PermissionDeniedError


async def apply_enable_change(user: models.User, enabled: bool) -> None:
    """Apply enable/disable change to user.
    
    Args:
        user: User model instance to update
        enabled: New enabled status
    """
    user.enabled = enabled
    if not user.enabled:
        await user.logout()


async def validate_admin_change(
    user: models.User, session: models.Session
) -> None:
    """Validate that admin status can be changed.
    
    Args:
        user: User model instance being updated
        session: Current session (to check if self-modification)
        
    Raises:
        PermissionDeniedError: If user tries to change their own admin status
    """
    if user.id == session.user_id:
        raise PermissionDeniedError


async def apply_admin_change(user: models.User, is_admin: bool) -> None:
    """Apply admin status change to user.
    
    Args:
        user: User model instance to update
        is_admin: New admin status
    """
    user.admin = is_admin
    await user.invalidate_access_tokens()


def apply_profile_updates(user: models.User, **fields: str | None) -> None:
    """Apply profile field updates to user.
    
    Args:
        user: User model instance to update
        **fields: Field names and values to update
    """
    # Define allowed profile fields to prevent silent failures
    allowed_fields = {
        'description', 'tags', 'first_name', 'last_name',
        'street', 'zip_code', 'city', 'country'
    }
    
    for field_name, value in fields.items():
        if field_name not in allowed_fields:
            continue  # Silently skip unknown fields for forward compatibility
        if value is not None and getattr(user, field_name) != value:
            setattr(user, field_name, value)


async def validate_user_creation(
    name: str, email: str, is_admin: bool
) -> None:
    """Validate user creation for uniqueness and email deliverability.
    
    Args:
        name: Username to validate
        email: Email address to validate
        is_admin: Whether the requester is an admin
        
    Raises:
        UserAlreadyExistsError: If username already exists
        EmailAlreadyExistsError: If email already exists
        InvalidEmailError: If non-admin uses invalid/undeliverable email
    """
    if await db.exists(models.User.filter_by_name(name)):
        raise UserAlreadyExistsError
    
    if await db.exists(models.User.filter_by_email(email)):
        raise EmailAlreadyExistsError
    
    if not is_admin and not await check_email_deliverability(email):
        raise InvalidEmailError
