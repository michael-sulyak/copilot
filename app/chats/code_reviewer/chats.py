import typing
from pathlib import Path

from ...models.openai.base import FunctionLLMTool, LLMFunctionCall, LLMFunctionCallOutput, LLMResponse
from ...models.openai.utils import gen_fake_tool_call_id, serialize_tool_output
from ...tools.additional_utils import get_changed_files
from ...tools.all import TOOLS_MAP
from ...tools.files import GitDiffTool, ReadFilesTool
from ...utils.common import gen_optimized_json
from ..base import AnswerBtn, Conversation, Message, Request
from ..llm_chat import Chat


class CodeManager(Chat):
    selected_work_dir: Path | None = None
    work_dirs: typing.Sequence[str]
    original_tool_names: list[str]
    connected_tool_names: set[str]
    welcome_message: Message | None = None
    files_are_supported = True

    def __init__(self, *args, **kwargs) -> None:
        self.work_dirs = kwargs.pop('work_dirs')
        self.original_tool_names = list(kwargs.pop('tools'))
        self.connected_tool_names = set(self.original_tool_names)
        if len(self.work_dirs) == 1:
            self.selected_work_dir = Path(self.work_dirs[0]).resolve()

        super().__init__(*args, **kwargs)

    async def get_welcome_message(self) -> Message:
        await self._gen_welcome_message()
        assert self.welcome_message is not None
        return self.welcome_message

    async def handle_callback(self, request: Request) -> None:
        if request.callback.startswith('work_dir:'):
            work_dir = Path(request.callback.removeprefix('work_dir:')).resolve()
            self._choose_work_dir(work_dir)
        elif request.callback.startswith('add_tool:'):
            tool_name = request.callback.removeprefix('add_tool:')
            self.connected_tool_names.add(tool_name)
        elif request.callback.startswith('remove_tool:'):
            tool_name = request.callback.removeprefix('remove_tool:')
            self.connected_tool_names.remove(tool_name)
        elif request.callback == 'add_context':
            self._add_context()
            changed_files = get_changed_files(self.selected_work_dir)
            changed_files_to_show = map(lambda x: f'* `{x}`', changed_files)
            await request.conversation.answer(
                Message(content=f'✅ Added context for:\n\n{"\n".join(changed_files_to_show)}'),
            )

        await self._gen_welcome_message()
        assert self.welcome_message is not None
        await request.conversation.update_message(self.welcome_message)

    def _choose_work_dir(self, work_dir: Path) -> None:
        self.selected_work_dir = work_dir

        if not self.selected_work_dir.exists() or not self.selected_work_dir.is_dir():
            raise ValueError(f'Invalid folder: {self.selected_work_dir}')

    async def _process(self, *, conversation: Conversation, model_params: dict) -> LLMResponse:
        async def logger(text: str) -> None:
            await conversation.answer(Message(content=text))

        return await self.model.execute(
            **model_params,
            tools=self._gen_tools(),
            max_steps=100,
            logger=logger,
            memory=self.memory,
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
                name= f'✅ Tool "{showed_tool_name}" (connected)' if tool_name in self.connected_tool_names else f'❌ Tool "{showed_tool_name}" (disconnected)',
                callback=f'remove_tool:{tool_name}' if tool_name in self.connected_tool_names else  f'add_tool:{tool_name}',
            ))

        return tuple(buttons)
