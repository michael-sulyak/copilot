import asyncio

import aiohttp
import html2text
from duckduckgo_search import DDGS
from newspaper import Article


class Searcher:
    @classmethod
    async def find(cls, query: str) -> list[dict]:
        search_results = DDGS().text(query, max_results=5)
        extracted_results = await Searcher._extract_info(tuple(
            result['href']
            for result in search_results
        ))
        return extracted_results

    @classmethod
    async def _extract_info(cls, urls: tuple[str, ...]) -> list[dict]:
        results = []
        html_converter = html2text.HTML2Text()
        html_converter.ignore_images = True

        async with aiohttp.ClientSession() as session:
            html_contents = await asyncio.gather(*(cls._fetch(session, url) for url in urls))

            for url, html in zip(urls, html_contents):
                article = Article(url)
                article.set_html(html)
                article.parse()
                results.append({
                    'title': article.title,
                    'url': url,
                    'markdown': html_converter.handle(article.html),
                })

        return results

    @staticmethod
    async def _fetch(session, url):
        async with session.get(url) as response:
            return await response.text()
