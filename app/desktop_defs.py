import typing

from pydantic import BaseModel, Field


class BodyContentAttachments(BaseModel):
    content: str
    attachments: list[str]


class Button(BaseModel):
    name: str
    callback: str


class GptBodyContent(BaseModel):
    content: str
    duration: float | None
    cost: float | None
    total_tokens: int | None


class BodyCallback(BaseModel):
    callback: str


class InputMessage(BaseModel):
    uuid: str
    from_: str = Field(..., alias='from')
    body: BodyContentAttachments | BodyCallback
    __ui__: dict | None = None  # It doesn't matter on backend side.

    class Config:
        allow_population_by_field_name = True

    @property
    def is_callback(self) -> bool:
        return isinstance(self.body, BodyCallback)


class OutputMessage(BaseModel):
    uuid: str
    type_: str = Field(..., alias='type')
    from_: str = Field(..., alias='from')
    body: GptBodyContent
    buttons: list[Button]
    timestamp: float

    class Config:
        allow_population_by_field_name = True


class OutputAction(BaseModel):
    type_: str = Field(..., alias='type')
    name: str
    payload: typing.Any
    timestamp: float

    class Config:
        allow_population_by_field_name = True
