from .. import config
from .base import BaseDialog, Message, Request


class GreetingsDialog(BaseDialog):
    async def get_welcome_message(self) -> Message | None:
        return Message(
            f'**Hello and welcome to our chat application!**\n\n'
            f'To get started, please follow these steps:\n'
            f'1. Update the API token in your main configuration file located at `{config.BASE_CONFIG_PATH}` so that you can use the models.\n'
            f'2. Remove this dialog from `{config.DIALOGS_PATH}` and modify other dialogs as needed.\n'
            f'3. Review the configurations in the `{config.CONFIGS_DIR}` directory to customize the app for your needs.\n\n'
            f'**Thank you for setting up your application!**',
        )

    async def handle(self, request: Request) -> None:
        await request.discussion.answer(
            Message(
                content='I\'m here to greet you, but I cannot perform any additional actions :(',
            ),
        )
