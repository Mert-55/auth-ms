import uvicorn

from settings import settings


def main() -> None:
    uvicorn.run(
        "api.app:app", host=settings.host, port=settings.port, reload=settings.reload
    )
