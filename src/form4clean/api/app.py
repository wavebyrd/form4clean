"""Local HTTP API and dashboard server.

Serves the JSON API under /api and the built React dashboard at /. Intended to run on
127.0.0.1 for a single user; there are no accounts.

Numbers are sent as decimal strings, never floats, so the dashboard shows exactly what the
engine computed.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import polars as pl
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.background import BackgroundTask

from .. import __version__
from ..client import parse_as_of
from ..config import ConfigError, load_settings, save_settings
from ..exports.writer import Format, write_frame, write_json
from ..market_data.providers import PROVIDERS
from ..query import TransactionFilter
from ..sec.client import SecError
from ..sec.edgar import Company, CompanyNotFoundError
from ..service import Form4Service, years_ago
from ..storage.store import StoreError
from ..summary import overview
from ..validation.flags import FLAGS
from ..versions import CLEANING_VERSION, SCHEMA_VERSION

STATIC_DIR = Path(__file__).parent / "static"


def _default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, pl.Series):
        return value.to_list()
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def json_response(data: Any, status_code: int = 200) -> Response:
    return Response(
        json.dumps(data, default=_default, ensure_ascii=False),
        media_type="application/json",
        status_code=status_code,
    )


@dataclass
class Job:
    id: str
    company: str
    state: Literal["running", "done", "error"] = "running"
    stage: str = "Resolving company"
    done: int = 0
    total: int = 0
    message: str | None = None
    summary: dict[str, Any] | None = None
    started: datetime = field(default_factory=datetime.now)


class FetchRequest(BaseModel):
    years: float | None = 5
    start: date | None = None
    end: date | None = None


class DataQuery(TransactionFilter):
    as_of: str | None = None
    reconcile: bool = True


class ListQuery(DataQuery):
    limit: int | None = None


class ExportQuery(DataQuery):
    dataset: Literal["clean", "raw", "quality", "manifest"] = "clean"
    format: Format = "csv"


def _filter_part(query: DataQuery) -> TransactionFilter:
    return TransactionFilter(**query.model_dump(include=set(TransactionFilter.model_fields)))


class SettingsUpdate(BaseModel):
    contact_email: str | None = None
    price_provider: str | None = None
    requests_per_second: float | None = None


def create_app(service: Form4Service | None = None) -> FastAPI:
    state: dict[str, Any] = {"service": service or Form4Service(load_settings())}
    jobs: dict[str, Job] = {}
    tasks: set[asyncio.Task[None]] = set()
    app = FastAPI(
        title="Form4Clean",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def svc() -> Form4Service:
        result: Form4Service = state["service"]
        return result

    @app.exception_handler(CompanyNotFoundError)
    async def _not_found(_: Request, exc: CompanyNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(ConfigError)
    async def _config(_: Request, exc: ConfigError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(SecError)
    async def _sec(_: Request, exc: SecError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    @app.exception_handler(StoreError)
    async def _store(_: Request, exc: StoreError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    def company(query: str) -> Company:
        return svc().require_company(query)

    # ---------------------------------------------------------------- meta

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "cleaning_version": CLEANING_VERSION,
        }

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        s = svc().settings
        return {
            "data_directory": str(s.home),
            "contact_email": s.contact_email,
            "user_agent": f"{s.app_name} {s.contact_email}" if s.contact_email else None,
            "requests_per_second": s.requests_per_second,
            "price_provider": s.price_provider,
            "csv_price_dir": str(s.prices_dir),
            "providers": [{"name": p.name, "label": p.label} for p in PROVIDERS.values()],
        }

    @app.put("/api/settings")
    def put_settings(update: SettingsUpdate) -> dict[str, Any]:
        changes = update.model_dump(exclude_none=True)
        if "price_provider" in changes and changes["price_provider"] not in PROVIDERS:
            raise HTTPException(400, f"Unknown provider {changes['price_provider']!r}.")
        settings = load_settings(svc().settings.home, **changes)
        save_settings(settings)
        state["service"] = Form4Service(settings)
        return get_settings()

    @app.get("/api/flags")
    def flags() -> list[dict[str, Any]]:
        return [
            {
                "code": f.code,
                "severity": str(f.severity),
                "title": f.title,
                "why": f.why,
                "action": f.action,
                "review_recommended": f.review,
            }
            for f in FLAGS.values()
        ]

    # ---------------------------------------------------------------- companies and jobs

    @app.get("/api/companies")
    def companies() -> Response:
        return json_response(svc().store.companies())

    @app.get("/api/resolve")
    async def resolve(q: str) -> dict[str, Any]:
        c = await svc().resolve(q)
        return {"cik": c.cik, "ticker": c.ticker, "name": c.name}

    @app.post("/api/companies/{query}/fetch")
    async def start_fetch(query: str, body: FetchRequest | None = None) -> dict[str, Any]:
        body = body or FetchRequest()
        svc().settings.user_agent()  # fail fast with a clear message if no email is set
        job = Job(id=uuid.uuid4().hex[:12], company=query.upper())
        jobs[job.id] = job
        start = body.start or years_ago(body.years or 5)

        def progress(stage: str, done: int, total: int) -> None:
            job.stage, job.done, job.total = "Downloading filings", done, total

        async def run() -> None:
            try:
                summary = await svc().fetch(query, start=start, end=body.end, progress=progress)
                job.stage = "Cleaning"
                result = await asyncio.to_thread(svc().clean, summary.company)
                job.summary = {**summary.as_dict(), "report": result.report.model_dump(mode="json")}
                job.state, job.stage = "done", "Done"
            except Exception as exc:  # reported to the user through the job status
                job.state, job.message = "error", str(exc) or exc.__class__.__name__

        task = asyncio.create_task(run())
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return {"job_id": job.id}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Unknown job.")
        return {
            "id": job.id,
            "company": job.company,
            "state": job.state,
            "stage": job.stage,
            "done": job.done,
            "total": job.total,
            "message": job.message,
            "summary": job.summary,
        }

    @app.get("/api/companies/{query}")
    def company_info(query: str) -> Response:
        c = company(query)
        info = svc().store.company(c.cik) or {}
        earliest, last = svc().store.coverage(c.cik)
        return json_response(
            {
                "cik": c.cik,
                "ticker": c.ticker,
                "name": c.name,
                "filings": info.get("filings", 0),
                "transactions": info.get("transactions", 0),
                "coverage_start": None if earliest in (None, date.min) else earliest,
                "full_history": earliest == date.min,
                "last_fetched": last,
            }
        )

    # ---------------------------------------------------------------- data

    def _dataset(query: str, q: DataQuery) -> tuple[Company, pl.DataFrame, Any]:
        c = company(query)
        try:
            cutoff = parse_as_of(q.as_of)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        df, report = svc().transactions(
            c, filters=_filter_part(q), as_of=cutoff, reconcile=q.reconcile
        )
        return c, df, report

    @app.get("/api/companies/{query}/transactions")
    def transactions(query: str, q: Annotated[ListQuery, Query()]) -> Response:
        _, df, _ = _dataset(query, q)
        df = df.sort("filing_timestamp", descending=True, nulls_last=True)
        total = df.height
        if q.limit:
            df = df.head(q.limit)
        rows = df.drop("source_values").to_dicts()
        return json_response({"count": total, "records": rows})

    @app.get("/api/companies/{query}/transactions/{transaction_id}")
    def transaction_detail(query: str, transaction_id: str) -> Response:
        c = company(query)
        df, _ = svc().transactions(c, filters=TransactionFilter(include_superseded=True))
        match = df.filter(pl.col("transaction_id") == transaction_id)
        if match.height == 0:
            raise HTTPException(404, f"No transaction {transaction_id}.")
        record = match.to_dicts()[0]
        record["source_values"] = json.loads(record["source_values"])
        return json_response(
            {"record": record, "cleaning_log": svc().store.cleaning_log(c.cik, transaction_id)}
        )

    @app.get("/api/companies/{query}/overview")
    def company_overview(query: str, months: int = 12) -> Response:
        c = company(query)
        df, report = svc().transactions(c, filters=TransactionFilter(include_superseded=True))
        return json_response(
            {
                "overview": overview(df, months=months),
                "status_distribution": report.status_distribution if report else {},
            }
        )

    @app.get("/api/companies/{query}/quality")
    def quality(query: str) -> Response:
        c = company(query)
        _, report = svc().transactions(c)
        return json_response(
            {"report": report, "amendment_links": svc().store.amendment_links(c.cik)}
        )

    @app.get("/api/companies/{query}/prices")
    async def prices(query: str, start: date | None = None, end: date | None = None) -> Response:
        c = company(query)
        end = end or date.today()
        start = start or end - timedelta(days=365 * 5)
        series = await svc().prices(c, start, end)
        return json_response(
            {
                "symbol": series.symbol,
                "provider": series.provider,
                "status": series.status,
                "message": series.message,
                "delayed": series.delayed,
                "adjusted": series.adjusted,
                "retrieved_at": series.retrieved_at,
                "bars": [b.as_dict() for b in series.bars],
            }
        )

    @app.get("/api/companies/{query}/export")
    def export(query: str, q: Annotated[ExportQuery, Query()]) -> Response:
        c, df, report = _dataset(query, q)
        dataset, fmt = q.dataset, q.format
        stem = (c.ticker or c.cik).lower()
        tmp = Path(tempfile.mkdtemp(prefix="form4clean_"))
        if dataset == "quality":
            path = write_json(
                report.model_dump(mode="json") if report else {},
                tmp / f"{stem}_quality_report.json",
            )
        elif dataset == "manifest":
            _, path = svc().export_bundle(
                c,
                tmp,
                fmt,
                filters=_filter_part(q),
                as_of=parse_as_of(q.as_of),
                reconcile=q.reconcile,
            )
        else:
            frame = svc().raw_transactions(c) if dataset == "raw" else df
            name = f"{stem}_{'raw_' if dataset == 'raw' else ''}transactions.{fmt}"
            path = write_frame(frame, tmp / name, fmt)
        return FileResponse(path, filename=path.name, background=BackgroundTask(_cleanup, tmp))

    # ---------------------------------------------------------------- dashboard

    if (STATIC_DIR / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> Response:
            candidate = STATIC_DIR / path
            if (
                path
                and candidate.is_file()
                and candidate.resolve().is_relative_to(STATIC_DIR.resolve())
            ):
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")
    else:

        @app.get("/", include_in_schema=False)
        def missing_frontend() -> HTMLResponse:
            return HTMLResponse(
                "<h1>Form4Clean</h1><p>The dashboard has not been built. Run "
                "<code>npm install && npm run build</code> in <code>frontend/</code>. "
                "The API is available at <a href='/api/docs'>/api/docs</a>.</p>"
            )

    return app


def _cleanup(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)
