#!/usr/bin/env python3
"""華南永昌同步資料 API。"""

import argparse
import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Optional

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from dotenv import load_dotenv

from entrust.config import SCRIPT_DIR
from entrust.api_data import (
    DataNotFoundError,
    available_dates,
    get_holdings,
    get_transaction_history,
    get_transactions,
)
from entrust.live_sync import LoginRequiredError, NavigationError, browser_worker


load_dotenv(SCRIPT_DIR / ".env", override=False)
API_TOKEN = os.getenv("ENTRUST_API_TOKEN", "")
API_VERSION = "1.7.0"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    browser_worker.start()
    try:
        yield
    finally:
        browser_worker.stop()

app = FastAPI(
    title="華南永昌同步資料 API",
    description="取得本機登入後擷取的持股與交易資料；API 不會代替使用者執行登入。",
    version=API_VERSION,
    lifespan=lifespan,
)


def verify_token(authorization: Optional[str] = Header(default=None)):
    """有設定 ENTRUST_API_TOKEN 時才要求 Bearer token。"""
    if not API_TOKEN:
        return
    expected = f"Bearer {API_TOKEN}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="API token 無效")


def _not_found(exc: DataNotFoundError):
    raise HTTPException(status_code=404, detail=str(exc)) from exc


def _bad_request(exc: ValueError):
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _browser_error(exc: Exception):
    status = 503 if isinstance(exc, LoginRequiredError) else 502
    raise HTTPException(status_code=status, detail=str(exc)) from exc


def _validate_stock_code(stock_code: Optional[str]) -> Optional[str]:
    if stock_code is None or not stock_code.strip():
        return None
    value = stock_code.strip().upper()
    if not re.fullmatch(r"[0-9A-Z]{1,10}", value):
        raise HTTPException(status_code=422, detail="stock_code 只能包含 1 到 10 位英文字母或數字")
    return value


def _validate_history_range(date_from: str, date_to: str) -> tuple[str, str]:
    try:
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="日期格式必須是 YYYY-MM-DD") from exc
    if start > end:
        raise HTTPException(status_code=422, detail="date_from 不可晚於 date_to")
    if (end - start).days > 183:
        raise HTTPException(status_code=422, detail="華南歷史對帳單單次查詢最多六個月")
    if (date.today() - start).days > 731:
        raise HTTPException(status_code=422, detail="華南歷史對帳單僅提供最近兩年資料")
    return date_from, date_to


@app.get("/health", summary="檢查 API 狀態")
@app.get("/api/v1/health", summary="檢查 API 狀態")
def health():
    return {
        "status": "ok",
        "version": API_VERSION,
        "session_detection": "all_context_pages",
        "login_mode": "local_manual",
        **browser_worker.status(),
    }


@app.get("/api/v1/dates", dependencies=[Depends(verify_token)], summary="列出可查詢日期")
def dates():
    return available_dates()


@app.get("/api/v1/statements/today", dependencies=[Depends(verify_token)], summary="查詢當日對帳單")
def statement_today(
    stock_code: Optional[str] = Query(default=None, description="個股代號；省略時查詢全部股票"),
):
    try:
        return browser_worker.submit("statement_today", stock_code=_validate_stock_code(stock_code))
    except (LoginRequiredError, NavigationError, RuntimeError) as exc:
        _browser_error(exc)


@app.get("/api/v1/statements/history", dependencies=[Depends(verify_token)], summary="查詢歷史對帳單")
def statement_history(
    date_from: str = Query(description="開始日期，YYYY-MM-DD"),
    date_to: str = Query(description="結束日期，YYYY-MM-DD；單次最多六個月"),
    stock_code: Optional[str] = Query(default=None, description="個股代號；省略時查詢全部股票"),
):
    date_from, date_to = _validate_history_range(date_from, date_to)
    try:
        return browser_worker.submit(
            "statement_history",
            date_from=date_from,
            date_to=date_to,
            stock_code=_validate_stock_code(stock_code),
        )
    except (LoginRequiredError, NavigationError, RuntimeError) as exc:
        _browser_error(exc)


@app.get("/api/v1/inventory", dependencies=[Depends(verify_token)], summary="查詢彙總庫存")
def inventory():
    try:
        browser_worker.submit("holdings")
        return get_holdings()
    except (LoginRequiredError, NavigationError, RuntimeError) as exc:
        _browser_error(exc)
    except DataNotFoundError as exc:
        _not_found(exc)


@app.get("/api/v1/profit-loss/unrealized", dependencies=[Depends(verify_token)], summary="查詢未實現損益")
def unrealized_profit_loss(
    stock_code: Optional[str] = Query(default=None, description="個股代號；省略時查詢全部股票"),
):
    try:
        return browser_worker.submit(
            "profit_loss",
            realized=False,
            stock_code=_validate_stock_code(stock_code),
        )
    except (LoginRequiredError, NavigationError, RuntimeError) as exc:
        _browser_error(exc)


@app.get("/api/v1/profit-loss/realized", dependencies=[Depends(verify_token)], summary="查詢已實現損益")
def realized_profit_loss(
    stock_code: Optional[str] = Query(default=None, description="個股代號；省略時查詢全部股票"),
):
    try:
        return browser_worker.submit(
            "profit_loss",
            realized=True,
            stock_code=_validate_stock_code(stock_code),
        )
    except (LoginRequiredError, NavigationError, RuntimeError) as exc:
        _browser_error(exc)


@app.get("/api/v1/holdings", dependencies=[Depends(verify_token)], summary="取得現有持股")
def holdings(
    sync_date: Optional[str] = Query(default=None, alias="date"),
    refresh: bool = Query(default=True, description="先從已登入的網站自動重新擷取"),
):
    try:
        if refresh and sync_date is None:
            browser_worker.submit("holdings")
        return get_holdings(sync_date)
    except (LoginRequiredError, NavigationError, RuntimeError) as exc:
        _browser_error(exc)
    except DataNotFoundError as exc:
        _not_found(exc)
    except ValueError as exc:
        _bad_request(exc)


@app.get("/api/v1/transactions/today", dependencies=[Depends(verify_token)], summary="取得今日交易")
def transactions_today(refresh: bool = Query(default=True, description="先從已登入的網站自動重新擷取")):
    try:
        if refresh:
            return browser_worker.submit("statement_today", stock_code=None)
        return get_transactions(date.today().isoformat())
    except (LoginRequiredError, NavigationError, RuntimeError) as exc:
        _browser_error(exc)
    except DataNotFoundError as exc:
        _not_found(exc)


@app.get("/api/v1/transactions", dependencies=[Depends(verify_token)], summary="取得指定日期交易")
def transactions(
    sync_date: str = Query(alias="date"),
    refresh: bool = Query(default=False, description="從網站重新擷取；歷史日期請使用 history 端點"),
):
    try:
        if refresh:
            browser_worker.submit("transactions", transaction_date=sync_date)
        return get_transactions(sync_date)
    except (LoginRequiredError, NavigationError, RuntimeError) as exc:
        _browser_error(exc)
    except DataNotFoundError as exc:
        _not_found(exc)
    except ValueError as exc:
        _bad_request(exc)


@app.get("/api/v1/transactions/history", dependencies=[Depends(verify_token)], summary="取得歷史交易")
def transaction_history(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = Query(default=1000, ge=1, le=10000),
    refresh: bool = Query(default=True, description="先自動開啟歷史交易查詢並擷取目前結果"),
):
    try:
        if refresh:
            end = date_to or date.today().isoformat()
            start = date_from or (date.fromisoformat(end) - timedelta(days=30)).isoformat()
            start, end = _validate_history_range(start, end)
            return browser_worker.submit(
                "statement_history",
                date_from=start,
                date_to=end,
                stock_code=None,
            )
        return get_transaction_history(date_from, date_to, limit)
    except (LoginRequiredError, NavigationError, RuntimeError) as exc:
        _browser_error(exc)
    except ValueError as exc:
        _bad_request(exc)


def main():
    parser = argparse.ArgumentParser(description="啟動華南永昌同步資料 API")
    parser.add_argument(
        "--host",
        default=os.getenv("ENTRUST_API_HOST", "127.0.0.1"),
        help="監聽位址（預設只允許本機，可由 .env 設定）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ENTRUST_API_PORT", "8000")),
        help="監聽連接埠（可由 .env 設定）",
    )
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"} and not API_TOKEN:
        parser.error("非本機監聽時必須先設定 ENTRUST_API_TOKEN")

    print(f"🔌 資料 API：http://{args.host}:{args.port}")
    print(f"📖 API 文件：http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
