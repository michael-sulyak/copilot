import typing
from pathlib import Path

from ..base import AnswerBtn, Discussion, Message, Request
from ..llm_chat import Dialog
from ...models.openai.base import FunctionLLMTool, LLMMessage, LLMResponse
from ...models.openai.constants import LLMMessageRoles
from ...models.openai.utils import format_tool_chat_message
from ...tools.additional_utils import get_changed_files
from ...tools.all import TOOLS_MAP
from ...tools.files import GitDiffTool, ReadFilesTool


class CodeManager(Dialog):
    selected_work_dir: Path
    work_dirs: typing.Sequence[str]
    tool_names: list[str]

    def __init__(self, *args, **kwargs) -> None:
        self.work_dirs = kwargs.pop('work_dirs')
        self.tool_names = list(kwargs.pop('tools'))
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
            await self._choose_work_dir(work_dir, discussion=request.discussion)
        elif request.callback.startswith('add_tool:'):
            tool_name = request.callback.removeprefix('add_tool:')
            self.tool_names.append(tool_name)
            await request.discussion.answer(
                Message(content=f'✅ Connected tool `{tool_name}`'),
            )
        elif request.callback == 'add_context':
            self._add_context()
            changed_files = get_changed_files(self.selected_work_dir)
            changed_files_to_show = map(lambda x: f'* `{x}`', changed_files)
            await request.discussion.answer(
                Message(content=f'✅ Added context for:\n\n{"\n".join(changed_files_to_show)}'),
            )

    async def _choose_work_dir(self, work_dir: Path, *, discussion: Discussion) -> None:
        self.selected_work_dir = work_dir

        if not self.selected_work_dir.exists() or not self.selected_work_dir.is_dir():
            raise ValueError(f'Invalid folder: {self.selected_work_dir}')

        await discussion.answer(Message(
            content=f'Work directory: `{self.selected_work_dir}`\n\nDo you want to add the diff now?',
            buttons=(
                AnswerBtn(name='Yes', callback='add_context'),
            ),
        ))

    async def _process(self, *, discussion: Discussion, model_params: dict) -> LLMResponse:
        async def logger(text: str) -> None:
            await discussion.answer(Message(content=text))

        return await self.model.execute(
            **model_params,
            tools=self._gen_tools(),
            max_steps=100,
            logger=logger,
        )

    def _add_context(self) -> None:
        changed_files = get_changed_files(self.selected_work_dir)

        self.memory.add_message(LLMMessage(
            role=LLMMessageRoles.SYSTEM,
            content=format_tool_chat_message(
                tool_name=GitDiffTool.description.name,
                stage='result',
                result=GitDiffTool(self.selected_work_dir).run(),
                for_user=False,
            ),
        ))
        self.memory.add_message(LLMMessage(
            role=LLMMessageRoles.SYSTEM,
            content=format_tool_chat_message(
                tool_name=ReadFilesTool.description.name,
                stage='result',
                result=ReadFilesTool(self.selected_work_dir).run(paths=changed_files),
                for_user=False,
            ),
        ))

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
