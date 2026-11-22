import asyncio
from collections.abc import Awaitable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapter.config import get_settings
from app.adapter.db import get_session
from app.adapter.repositories.source_browser import SourceBrowserSqlRepository
from app.adapter.s3 import read_object_prefix
from app.domain.source_browser import SourceBrowserFile, SourceBrowserSnapshot, SourceBrowserTree
from app.usecase.source_browser import (
    SourceBrowserNotFoundError,
    SourceBrowserRequestError,
    SourceBrowserUsecase,
)

router = APIRouter(prefix="/sources/{source_id}/source-browser", tags=["source-browser"])


def build_usecase(session: Annotated[AsyncSession, Depends(get_session)]) -> SourceBrowserUsecase:
    settings = get_settings()

    async def read_bytes(key: str, max_bytes: int) -> bytes | None:
        return await asyncio.to_thread(read_object_prefix, settings, key, max_bytes)

    return SourceBrowserUsecase(
        SourceBrowserSqlRepository(session),
        read_bytes,
        settings.source_browser_preview_max_bytes,
        settings.source_browser_page_size,
    )


BrowserDep = Annotated[SourceBrowserUsecase, Depends(build_usecase)]


async def _result[Result](operation: Awaitable[Result]) -> Result:
    try:
        return await operation
    except SourceBrowserNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SourceBrowserRequestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("")
async def get_source_browser_snapshot(source_id: int, browser: BrowserDep) -> SourceBrowserSnapshot:
    return await _result(browser.snapshot(source_id))


@router.get("/{snapshot_id}/tree")
async def get_source_browser_tree(
    source_id: int,
    snapshot_id: int,
    browser: BrowserDep,
    branch: str = "",
    folder: str = "",
    cursor: Annotated[str | None, Query(max_length=83)] = None,
) -> SourceBrowserTree:
    return await _result(browser.tree(source_id, snapshot_id, branch, folder, cursor))


@router.get("/{snapshot_id}/file")
async def get_source_browser_file(
    source_id: int, snapshot_id: int, path: str, browser: BrowserDep, branch: str = ""
) -> SourceBrowserFile:
    return await _result(browser.file(source_id, snapshot_id, branch, path))
