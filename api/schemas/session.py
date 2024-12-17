import jwt
from pydantic import ConfigDict, BaseModel, Field

from .user import User
from ..utils.docs import example, get_example


class Session(BaseModel):
    id: str = Field(description="Unique identifier for the session")
    user_id: str = Field(description="Unique identifier for the user")
    device_name: str = Field(description="Name of the device")
    last_update: float = Field(
        description="Timestamp of the last time an access token was created"
    )

    model_config = ConfigDict(
        **example(
            id="74193090-b88c-4984-9e51-da9cd3372e62",
            user_id="a13e63b1-9830-4604-8b7f-397d2c29955e",  # get_example(User)["id"],
            device_name="test device",
            last_update=1615725447.182818,
        )
    )


class Login(BaseModel):
    name_or_email: str = Field(description="Unique username or email")
    password: str = Field(description="Password of the user")


class LoginResponse(BaseModel):
    user: User = Field(description="User that was logged in")
    session: Session = Field(description="Session that was created")
    access_token: str = Field(
        description="Access token that can be used to authenticate requests"
    )
    refresh_token: str = Field(
        description="Refresh token that can be used to request a new access token"
    )

    model_config = ConfigDict(
        **example(  # noqa: S106
            user=get_example(User),
            session=get_example(Session),
            access_token=jwt.encode(
                {
                    "user_id": "a13e63b1-9830-4604-8b7f-397d2c29955e",  # get_example(User)["id"],
                    "session_id": "a13e63b1-9830-4604-8b7f-397d2c29955e",  # get_example(Session)["id"],
                    "exp": 0,
                },
                "secret",
            ),
            refresh_token="KN4nF8BsiElQi_OoDYQ2BgVdhVirhTw67vOzfHutjONvazRXLsboZ__UG-oI-II3LoMNv9tgd6YBGYRGxNK7Ug",
        )
    )
