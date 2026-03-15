import typing
import uuid
from pathlib import Path

from ..base import AnswerBtn, Conversation, Message, Request
from ..llm_chat import Dialog
from ...models.openai.base import FunctionLLMTool, LLMFunctionCall, LLMFunctionCallOutput, LLMResponse
from ...models.openai.utils import serialize_tool_output
from ...tools.additional_utils import get_changed_files
from ...tools.all import TOOLS_MAP
from ...tools.files import GitDiffTool, ReadFilesTool
from ...utils.common import gen_optimized_json


class CodeManager(Dialog):
    selected_work_dir: Path
    work_dirs: typing.Sequence[str]
    original_tool_names: list[str]
    tool_names: list[str]

    def __init__(self, *args, **kwargs) -> None:
        self.work_dirs = kwargs.pop('work_dirs')
        self.original_tool_names = list(kwargs.pop('tools'))
        self.tool_names = self.original_tool_names.copy()
        super().__init__(*args, **kwargs)

    async def get_welcome_message(self) -> Message:
        if self.tool_names:
            tools_info = (
                '\n\nConnected tools:\n'
                + '\n'.join(f'* `{TOOLS_MAP[tool_name].description.name}`' for tool_name in self.tool_names)
            )
        else:
            tools_info = '\n\nNo tools connected.'

        content: str

        if len(self.work_dirs) > 1:
            content = f'What work directory do you want to use?{tools_info}'
            buttons = tuple(
                AnswerBtn(name=f'📁 {work_dir}', callback=f'work_dir:{work_dir}')
                for work_dir in self.work_dirs
            )
        else:
            self.selected_work_dir = Path(self.work_dirs[0]).resolve()
            content = (
                f'Using work directory: `{self.selected_work_dir}`\n'
                f'(only one available, selected automatically and added the context)'
                f'{tools_info}'
            )
            buttons = (
                AnswerBtn(name='🗂️ Add context (GIT diff, etc.)', callback='add_context'),
            )

        buttons += self._gen_buttons_with_additional_tools()

        return Message(content=content, buttons=buttons)

    async def handle_callback(self, request: Request) -> None:
        if request.callback.startswith('work_dir:'):
            work_dir = Path(request.callback.removeprefix('work_dir:')).resolve()
            await self._choose_work_dir(work_dir, conversation=request.conversation)
        elif request.callback.startswith('add_tool:'):
            tool_name = request.callback.removeprefix('add_tool:')
            self.tool_names.append(tool_name)
            await request.conversation.answer(
                Message(content=f'✅ Connected tool `{tool_name}`'),
            )
        elif request.callback == 'add_context':
            self._add_context()
            changed_files = get_changed_files(self.selected_work_dir)
            changed_files_to_show = map(lambda x: f'* `{x}`', changed_files)
            await request.conversation.answer(
                Message(content=f'✅ Added context for:\n\n{"\n".join(changed_files_to_show)}'),
            )

    async def _choose_work_dir(self, work_dir: Path, *, conversation: Conversation) -> None:
        self.selected_work_dir = work_dir

        if not self.selected_work_dir.exists() or not self.selected_work_dir.is_dir():
            raise ValueError(f'Invalid folder: {self.selected_work_dir}')

        await conversation.answer(Message(
            content=f'Work directory: `{self.selected_work_dir}`\n\nDo you want to add the diff now?',
            buttons=(
                AnswerBtn(name='Yes', callback='add_context'),
            ),
        ))

    async def _process(self, *, conversation: Conversation, model_params: dict) -> LLMResponse:
        async def logger(text: str) -> None:
            await conversation.answer(Message(content=text))

        return await self.model.execute(
            **model_params,
            tools=self._gen_tools(),
            max_steps=100,
            logger=logger,
        )

    def _add_context(self) -> None:
        if not hasattr(self, 'selected_work_dir'):
            raise ValueError('Work directory is not selected')

        changed_files = list(dict.fromkeys(map(str, get_changed_files(self.selected_work_dir))))

        git_diff_tool = GitDiffTool(self.selected_work_dir)
        git_diff_call_id = f'context_{uuid.uuid4().hex}'
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
        read_files_call_id = f'context_{uuid.uuid4().hex}'
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
            for tool_name in self.tool_names
        )

    def _gen_buttons_with_additional_tools(self) -> tuple[AnswerBtn, ...]:
        additional_tools = sorted(set(TOOLS_MAP.keys()) - set(self.tool_names))

        return tuple(
            AnswerBtn(name=f'🔨 Connect tool "{additional_tool}"', callback=f'add_tool:{additional_tool}')
            for additional_tool in additional_tools
        )
