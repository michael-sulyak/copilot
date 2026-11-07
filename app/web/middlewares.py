import typing
from urllib.parse import urlsplit

from aiohttp import web

from .. import config


@web.middleware
async def browser_security_middleware(request: web.Request, handler: typing.Callable) -> web.StreamResponse:
    allowed_hosts = {urlsplit(origin).netloc.lower() for origin in config.ALLOWED_ORIGINS}

    if request.host.lower() not in allowed_hosts:
        raise web.HTTPForbidden(text='Request host is not allowed.')

    origin = request.headers.get('Origin')

    if origin and origin not in config.ALLOWED_ORIGINS:
        raise web.HTTPForbidden(text='Browser origin is not allowed.')

    if not origin and request.path in {'/rpc', '/upload-file'} and request.headers.get('Sec-Fetch-Site') == 'cross-site':
        raise web.HTTPForbidden(text='Cross-site API requests are not allowed.')

    response = await handler(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'

    if request.path.startswith(config.SHOWED_UPLOADS_DIR.rstrip('/') + '/'):
        # Uploaded HTML and SVG must not execute scripts on the application origin.
        response.headers['Content-Security-Policy'] = "sandbox; default-src 'none'; img-src data:"

    return response


def index_middleware(index='index.html') -> typing.Callable:
    async def middleware_factory(app, handler):
        async def index_handler(request):
            try:
                filename = request.match_info['filename']
                if not filename:
                    filename = index
                if filename.endswith('/'):
                    filename += index
                request.match_info['filename'] = filename
            except KeyError:
                pass

            return await handler(request)

        return index_handler

    return middleware_factory
