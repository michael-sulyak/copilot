import asyncio
import datetime
import logging

import aiohttp
import html2text
from duckduckgo_search import DDGS
from newspaper import Article

from ..memory import BaseMemory
from ..models.openai.base import GPT4mini, GPTMessage, GPTResponse
from ..models.openai.constants import GPTRoles
from ..utils.common import gen_optimized_json
from .base import BaseDialog, DialogError, Message, Request
from .profiles import BaseProfile


TPL_PREPARE_ANSWER = """
User requested it:
```
{user_request}
```

I found this info in Google:
```
{search_results}
```

Parse the search results to generate a comprehensive answer for the user.
You can add additional info from yourself if needed.
Send me prepared text that I can show to the user as it is.
"""


class Searcher(BaseDialog):
    profile: BaseProfile
    memory: BaseMemory

    def __init__(
        self, *,
        profile: BaseProfile,
        memory: BaseMemory,
        files_are_supported: bool = False,
    ) -> None:
        self.profile = profile
        self.memory = memory
        self.files_are_supported = files_are_supported

        # if context := self.profile.get_context():
        #     self.memory.add_context(GPTMessage(role=GPTRoles.SYSTEM, content=context))

    async def handle(self, request: Request) -> None:
        """
        List of parameters for ChatCompletion:
        https://holypython.com/python-api-tutorial/learn-openai-official-chatgpt-api-comprehensive-developer-tutorial/
        #chatgpt-api-completion-parameters
        """

        started_at = datetime.datetime.now()

        await request.discussion.set_text_status('Generating query...')
        query = await self.generate_query(request)

        await request.discussion.set_text_status(f'Searching info for "{query.content}"...')
        search_results = await self.find_info(query.content)

        await request.discussion.set_text_status('Extracting data...')
        extracted_results = await ArticleExtractor().extract_info(tuple(
            result['href']
            for result in search_results
        ))

        await request.discussion.set_text_status('Preparing answer...')
        final_response = await self.prepare_answer(request, extracted_results)

        answer = Message(
            content=final_response.content,
            duration=datetime.datetime.now() - started_at,
            cost=final_response.cost + query.cost,
            total_tokens=final_response.total_tokens + query.total_tokens,
        )

        await request.discussion.answer(answer)

    async def generate_query(self, request: Request) -> GPTResponse:
        prompt = (
            'Generate query string for Google to find appropriate info '
            '(use also context and history of messages for it) for the user request.\n'
            'Return only the query string that can be put directly in search input in Google.\n'
            'User request:\n'
            f'{request.content}'
        )

        self.memory.add_message(GPTMessage(
            role=GPTRoles.SYSTEM,
            content=prompt,
        ))

        logging.info('History: %s', self.memory.get_buffer())

        try:
            response = await GPT4mini.process(
                messages=self.memory.get_buffer(),
                temperature=self.profile.temperature,
            )
        except Exception as e:
            logging.exception(e)
            raise DialogError(str(e)) from e
        finally:
            self.memory.pop_message()

        return GPTResponse(
            content=response.content.strip('"'),
            cost=response.cost,
            total_tokens=response.total_tokens,
            func_call=response.func_call,
            duration=response.duration,
            original_response=response.original_response,
        )

    async def clear_history(self) -> None:
        self.memory.clear()

    @staticmethod
    async def find_info(query: str) -> list[dict]:
        return DDGS().text(query, max_results=5)

    async def prepare_answer(self, request: Request, search_results: list[dict]) -> GPTResponse:
        self.memory.add_message(GPTMessage(
            role=GPTRoles.USER,
            content=TPL_PREPARE_ANSWER.strip().format(
                user_request=request.content,
                search_results=gen_optimized_json(search_results),
            ),
        ))

        logging.info('History: %s', self.memory.get_buffer())

        try:
            response = await GPT4mini.process(
                messages=self.memory.get_buffer(),
                temperature=self.profile.temperature,
            )
        except Exception as e:
            logging.exception(e)
            raise DialogError(str(e)) from e

        self.memory.add_message(GPTMessage(role=GPTRoles.ASSISTANT, content=response.content))

        return response


class ArticleExtractor:
    @staticmethod
    async def fetch(session, url):
        async with session.get(url) as response:
            return await response.text()

    @classmethod
    async def extract_info(cls, urls: tuple[str, ...]) -> list[dict]:
        results = []
        h = html2text.HTML2Text()
        h.ignore_images = True

        async with aiohttp.ClientSession() as session:
            html_contents = await asyncio.gather(*(cls.fetch(session, url) for url in urls))

            for url, html in zip(urls, html_contents):
                article = Article(url)
                article.set_html(html)
                article.parse()
                # article.nlp()
                results.append({
                    'title': article.title,
                    'url': url,
                    'markdown': h.handle(article.html),
                    # 'summary': article.summary,
                })

        return results
