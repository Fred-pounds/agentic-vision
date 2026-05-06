from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import create_router
from app.core.config import get_settings
from app.storage.database import Database
from app.services.repository import Repository


def create_app() -> FastAPI:
    settings = get_settings()
    db = Database(settings.database_path)
    repo = Repository(db)

    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(create_router(settings, repo))
    return app


app = create_app()

