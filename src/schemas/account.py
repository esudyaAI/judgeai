"""Account HTTP contracts. Secret input values are never included in responses."""

import base64
import binascii

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    firstName: str = Field(default="", max_length=100)
    lastName: str = Field(default="", max_length=100)
    email: str = Field(default="", max_length=254)
    position: str = Field(default="", max_length=200)
    org: str = Field(default="", max_length=200)
    region: str = Field(default="", max_length=100)
    avatar: str = Field(default="", max_length=350000)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        if value and (value.count("@") != 1 or not all(value.split("@")) or " " in value):
            raise ValueError("Укажите корректный email")
        return value

    @field_validator("avatar")
    @classmethod
    def valid_avatar(cls, value):
        if not value:
            return value
        prefix, _, encoded = value.partition(",")
        signatures = {
            "data:image/png;base64": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
            "data:image/jpeg;base64": lambda b: b.startswith(b"\xff\xd8\xff"),
            "data:image/webp;base64": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
        }
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Некорректное фото") from None
        if prefix not in signatures or not signatures[prefix](data) or len(data) > 256 * 1024:
            raise ValueError("Фото: PNG, JPEG или WebP, не более 256 КБ")
        return value


class PasswordChange(BaseModel):
    current_password: SecretStr
    new_password: SecretStr = Field(min_length=12, max_length=1024)


class DeleteCases(BaseModel):
    password: SecretStr
    confirmation: str
