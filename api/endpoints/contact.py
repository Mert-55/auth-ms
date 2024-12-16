"""Endpoints for contact/support api"""

from typing import Any

from fastapi import APIRouter

from api.exceptions.contact import CouldNotSendMessageError
from api.schemas.contact import Message
from api.settings import settings
from api.utils.docs import responses
from api.utils.email import send_email


router = APIRouter()


@router.post("/contact", responses=responses(bool, CouldNotSendMessageError))
async def send_message(data: Message) -> Any:
    """
    Send a message to the support team.

    A recaptcha response is required if recaptcha is enabled (see `GET /recaptcha`).
    """

    if not settings.contact_email:
        raise CouldNotSendMessageError

    try:
        await send_email(
            settings.contact_email,
            f"[Contact Form] {data.subject}",
            f"Message from {data.name} ({data.email}):\n\n{data.message}",
            reply_to=data.email,
        )
    except ValueError:
        raise CouldNotSendMessageError

    return True
