"""Stream disposal adapted from the repository's simple search server.py."""
import anyio
import httpx


async def close_stream(response: httpx.Response) -> None:
    with anyio.CancelScope(shield=True):
        try:
            await response.aclose()
        except httpx.HTTPError:
            # Transport diagnostics may include the upstream JWT-bearing URL.
            pass
