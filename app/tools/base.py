import abc
import dataclasses
import inspect
import typing

from ..models.openai.base import FunctionLLMTool, LLMFunctionCall
from .additional_utils import gen_tool_error


class BaseLLMToolFabric(abc.ABC):
    description: typing.ClassVar[FunctionLLMTool]

    @abc.abstractmethod
    def run(self, *args, **kwargs) -> str:
        """
        Tool implementation, accepting keyword arguments from the model.
        May return a result or an awaitable; describe() adapts the LLMFunctionCall.
        """

    def describe(self) -> FunctionLLMTool:
        params = {
            field.name: getattr(self.description, field.name)
            for field in dataclasses.fields(self.description)
        }

        async def wrapper(call: LLMFunctionCall) -> str:
            try:
                if call.args is not None and not isinstance(call.args, dict):
                    raise TypeError('Tool arguments must be a JSON object.')

                result = self.run(**(call.args or {}))
                return await result if inspect.isawaitable(result) else result
            except TypeError as e:
                return gen_tool_error(
                    tool=self.description.name,
                    error_type='InvalidArguments',
                    message=str(e),
                    provided_args=call.args or {},
                )
            except Exception as e:
                return gen_tool_error(
                    tool=self.description.name,
                    error_type='ToolExecutionFailed',
                    message=str(e),
                    provided_args=call.args or {},
                )

        params['func'] = wrapper
        return FunctionLLMTool(**params)
