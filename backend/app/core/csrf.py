"""Cross-site request protection.

The API has no tokens: in production the browser sends Caddy's basic-auth credentials with
every request to the domain, including ones a different website makes it send; in development
the API on localhost has no auth at all. A JSON body already forces a CORS preflight, but a
body-less POST (reindex, LLM extraction, idea refresh) is a "simple" request any page can fire.

Browsers say where a request came from in `Sec-Fetch-Site`. Writes are accepted only from the
app itself (`same-origin`) or from no site at all (`none`: typed URLs, bookmarks). Clients
that send no such header (curl, scripts, the eval runners) are not browsers, and pass.
"""

from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
ALLOWED_SITES = {b"same-origin", b"none"}


class CrossSiteGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            site = dict(scope["headers"]).get(b"sec-fetch-site")
            if site is not None and site.lower() not in ALLOWED_SITES:
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [(b"content-type", b"application/json")],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b'{"detail":"cross-site request refused"}',
                    }
                )
                return
        await self.app(scope, receive, send)
