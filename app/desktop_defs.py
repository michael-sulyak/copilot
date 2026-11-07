import typing

from pydantic import BaseModel, Field


class BodyContentAttachments(BaseModel):
    content: str = Field(default='', max_length=1_000_000)
    attachments: list[str] = Field(default_factory=list, max_length=20)


class Button(BaseModel):
    name: str
    callback: str


class GptBodyContent(BaseModel):
    content: str
    duration: float | None
    cost: float | None
    total_tokens: int | None


class BodyCallback(BaseModel):
    callback: str = Field(min_length=1, max_length=4096)


class InputMessage(BaseModel):
    uuid: str = Field(min_length=1, max_length=128)
    chat_uuid: str = Field(min_length=1, max_length=128)
    from_: typing.Literal['user'] = Field(..., alias='from')
    body: BodyCallback | BodyContentAttachments
    __ui__: dict | None = None  # It doesn't matter on backend side.

    class Config:
        validate_by_name = True

    @property
    def is_callback(self) -> bool:
        return isinstance(self.body, BodyCallback)


class OutputMessage(BaseModel):
    uuid: str
    chat_uuid: str
    type_: str = Field(..., alias='type')
    from_: str = Field(..., alias='from')
    body: GptBodyContent
    buttons: list[Button]
    timestamp: float
    revision: int = 0

    class Config:
        validate_by_name = True


class OutputAction(BaseModel):
    chat_uuid: str
    type_: str = Field(..., alias='type')
    name: str
    payload: typing.Any
    timestamp: float
    revision: int = 0

    class Config:
        validate_by_name = True


class OutputToolCall(BaseModel):
    uuid: str
    chat_uuid: str
    type_: str = Field(..., alias='type')
    payload: typing.Any
    timestamp: float
    revision: int = 0

    class Config:
        validate_by_name = True
