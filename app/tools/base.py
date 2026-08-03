import abc
import dataclasses
import typing

from .additional_utils import gen_tool_error
from ..models.openai.base import FunctionLLMTool, LLMFunctionCall


class BaseLLMToolFabric(abc.ABC):
    description: typing.ClassVar[FunctionLLMTool]

    @abc.abstractmethod
    def run(self, *args, **kwargs) -> str:
        """
        Tool executor used by the LLM loop.
        NOTE: BaseLLM.execute calls tool.func(call), so we accept LLMToolCall here.
        """

    def describe(self) -> FunctionLLMTool:
        params = {
            field.name: getattr(self.description, field.name)
            for field in dataclasses.fields(self.description)
        }

        def wrapper(call: LLMFunctionCall) -> str:
            try:
                return self.run(**(call.args or {}))
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
