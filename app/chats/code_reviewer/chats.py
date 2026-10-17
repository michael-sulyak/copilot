import asyncio
import typing
import uuid
from pathlib import Path

from ...models.openai.base import (
    BaseStepController,
    FunctionLLMTool,
    LLMFunctionCall,
    LLMFunctionCallOutput,
    LLMResponse,
    LLMToolCallAggregatedTracker,
)
from ...models.openai.utils import gen_fake_tool_call_id, serialize_tool_output
from ...tools.additional_utils import get_changed_files
from ...tools.all import TOOLS_MAP
from ...tools.files import GitDiffTool, ReadFilesTool
from ...utils.common import gen_optimized_json
from ..base import AnswerBtn, ChatCallbackHandlerMixin, Conversation, Message, Request, ToolCall
from ..llm_chat import Chat


class CodeManagerStepController(BaseStepController):
    code_manager: 'CodeManager'
    conversation: Conversation

    def __init__(self, *, code_manager: 'CodeManager', conversation: Conversation) -> None:
        self.code_manager = code_manager
        self.conversation = conversation

    async def __call__(self, *, current_tokens: int) -> None:
        has_achieved_desired_limit = self.code_manager.desired_max_tokens is not None and current_tokens > self.code_manager.desired_max_tokens

        if has_achieved_desired_limit:
            callback_uuid_to_continue = str(uuid.uuid4())
            callback_uuid_to_stop = str(uuid.uuid4())
            message = Message(
                content='You have reached desired max tokens',
                buttons=(
                    AnswerBtn(name='Continue', callback=callback_uuid_to_continue),
                    AnswerBtn(name='Stop', callback=callback_uuid_to_stop),
                ),
            )

            target_event = asyncio.Event()
            has_stopped = False

            def _continue(request: Request) -> None:
                self.code_manager.desired_max_tokens = None
                target_event.set()

            def _stop(request: Request) -> None:
                nonlocal has_stopped

                has_stopped = True
                target_event.set()

            self.code_manager._register_once_time_callback_handler(
                name=callback_uuid_to_continue,
                func=_continue,
            )
            self.code_manager._register_once_time_callback_handler(
                name=callback_uuid_to_stop,
                func=_stop,
            )

            await self.conversation.answer(message)
            await target_event.wait()

            if has_stopped:
                raise RuntimeError('There are too few tokens left to answer.')

            await self.conversation.set_text_status('Continue processing...')


class CodeManager(ChatCallbackHandlerMixin, Chat):
    selected_work_dir: Path | None = None
    work_dirs: typing.Sequence[str]
    original_tool_names: list[str]
    connected_tool_names: set[str]
    welcome_message: Message | None = None
    files_are_supported = True
    desired_max_tokens: int | None

    def __init__(self, *args, **kwargs) -> None:
        self.work_dirs = kwargs.pop('work_dirs')
        self.original_tool_names = list(kwargs.pop('tools'))
        self.desired_max_tokens = kwargs.pop('desired_max_tokens')
        self.connected_tool_names = set(self.original_tool_names)
        if len(self.work_dirs) == 1:
            self.selected_work_dir = Path(self.work_dirs[0]).resolve()

        super().__init__(*args, **kwargs)

    async def get_welcome_message(self) -> Message:
        await self._gen_welcome_message()
        assert self.welcome_message is not None
        return self.welcome_message

    async def handle_callback(self, request: Request) -> None:
        has_influence_on_welcome_message = False

        if request.callback.startswith('work_dir:'):
            work_dir = Path(request.callback.removeprefix('work_dir:')).resolve()
            self._choose_work_dir(work_dir)
            has_influence_on_welcome_message = True
        elif request.callback.startswith('add_tool:'):
            tool_name = request.callback.removeprefix('add_tool:')
            self.connected_tool_names.add(tool_name)
            has_influence_on_welcome_message = True
        elif request.callback.startswith('remove_tool:'):
            tool_name = request.callback.removeprefix('remove_tool:')
            self.connected_tool_names.remove(tool_name)
            has_influence_on_welcome_message = True
        elif request.callback == 'add_context':
            self._add_context()
            changed_files = get_changed_files(self.selected_work_dir)
            changed_files_to_show = map(lambda x: f'* `{x}`', changed_files)
            await request.conversation.answer(
                Message(content=f'✅ Added context for:\n\n{"\n".join(changed_files_to_show)}'),
            )
        else:
            self._handle_once_time_callbacks(request)

        if has_influence_on_welcome_message:
            await self._gen_welcome_message()
            assert self.welcome_message is not None
            await request.conversation.update_message(self.welcome_message)

    def _choose_work_dir(self, work_dir: Path) -> None:
        self.selected_work_dir = work_dir

        if not self.selected_work_dir.exists() or not self.selected_work_dir.is_dir():
            raise ValueError(f'Invalid folder: {self.selected_work_dir}')

    async def _process(self, *, conversation: Conversation, model_params: dict) -> LLMResponse:
        call_tracker_message: ToolCall | None = None

        async def logger(data: str | LLMToolCallAggregatedTracker) -> None:
            nonlocal call_tracker_message

            if isinstance(data, LLMToolCallAggregatedTracker):
                if call_tracker_message is None:
                    call_tracker_message = ToolCall(payload=data.dump())
                    await conversation.answer(call_tracker_message)
                else:
                    call_tracker_message = ToolCall(uuid=call_tracker_message.uuid, payload=data.dump())
                    await conversation.update_message(call_tracker_message)
            else:
                await conversation.answer(Message(content=data))

        return await self.model.execute(
            **model_params,
            tools=self._gen_tools(),
            max_steps=100,
            logger=logger,
            memory=self.memory,
            step_controller=CodeManagerStepController(
                code_manager=self,
                conversation=conversation,
            ),
        )

    def _add_context(self) -> None:
        if not hasattr(self, 'selected_work_dir'):
            raise ValueError('Work directory is not selected')

        changed_files = list(dict.fromkeys(map(str, get_changed_files(self.selected_work_dir))))

        git_diff_tool = GitDiffTool(self.selected_work_dir)
        git_diff_call_id = gen_fake_tool_call_id()
        git_diff_args: dict[str, typing.Any] = {}

        self.memory.add_message(
            LLMFunctionCall(
                name=git_diff_tool.describe().name,
                args=git_diff_args,
                raw_args=gen_optimized_json(git_diff_args),
                is_valid=True,
                call_id=git_diff_call_id,
            ),
        )
        self.memory.add_message(
            LLMFunctionCallOutput(
                call_id=git_diff_call_id,
                output=gen_optimized_json(git_diff_tool.run()),
            ),
        )

        readable_files: list[str] = []

        for changed_file in changed_files:
            file_path = Path(changed_file)
            abs_path = file_path if file_path.is_absolute() else self.selected_work_dir / file_path

            if abs_path.exists() and abs_path.is_file():
                readable_files.append(changed_file)

        if not readable_files:
            return

        read_files_tool = ReadFilesTool(self.selected_work_dir)
        read_files_call_id = gen_fake_tool_call_id()
        read_files_args = {'paths': readable_files}

        self.memory.add_message(
            LLMFunctionCall(
                name=read_files_tool.describe().name,
                args=read_files_args,
                raw_args=gen_optimized_json(read_files_args),
                is_valid=True,
                call_id=read_files_call_id,
            ),
        )
        self.memory.add_message(
            LLMFunctionCallOutput(
                call_id=read_files_call_id,
                output=serialize_tool_output(read_files_tool.run(paths=readable_files)),
            ),
        )

    def _gen_tools(self) -> tuple[FunctionLLMTool, ...]:
        return tuple(
            TOOLS_MAP[tool_name](self.selected_work_dir).describe()
            for tool_name in self.connected_tool_names
        )

    async def _gen_welcome_message(self) -> None:
        content: str

        if self.selected_work_dir:
            content = f'Work directory: `{self.selected_work_dir}`'
            buttons = (
                AnswerBtn(name='🗂️ Add context (GIT diff, etc.)', callback='add_context'),
            )
        else:
            content = 'What work directory do you want to use?'
            buttons = tuple(
                AnswerBtn(name=f'📁 {work_dir}', callback=f'work_dir:{work_dir}')
                for work_dir in self.work_dirs
            )

        buttons += self._gen_buttons_with_tools()

        params: dict[str, typing.Any] = {'content': content, 'buttons': buttons}

        if self.welcome_message:
            params['uuid'] = self.welcome_message.uuid

        self.welcome_message = Message(**params)

    def _gen_buttons_with_tools(self) -> tuple[AnswerBtn, ...]:
        buttons = []

        for tool_name in self.original_tool_names:
            showed_tool_name = TOOLS_MAP[tool_name].description.showed_name or TOOLS_MAP[tool_name].description.name

            buttons.append(AnswerBtn(
                name=f'✅ Tool "{showed_tool_name}" (connected)' if tool_name in self.connected_tool_names else f'❌ Tool "{showed_tool_name}" (disconnected)',
                callback=f'remove_tool:{tool_name}' if tool_name in self.connected_tool_names else f'add_tool:{tool_name}',
            ))

        return tuple(buttons)
