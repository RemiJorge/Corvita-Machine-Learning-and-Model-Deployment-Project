"""FastAPI routes, middleware, and application factory."""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from icu.api.request_log import RequestLogWriter, build_log_record
from icu.api.schemas import ErrorResponse, HealthResponse, PredictRequest, PredictResponse
from icu.api.service import predict_from_request
from icu.artifacts import load_model
from icu.config import load_config

logger = logging.getLogger(__name__)


def serving_config(config_path: Path | str | None = None) -> dict[str, Any]:
    """Load config and apply MODEL_VERSION and MODELS_DIR environment overrides."""
    config = load_config(config_path)
    config = dict(config)
    paths = dict(config["paths"])
    models_dir = os.environ.get("MODELS_DIR")
    if models_dir:
        paths["models_dir"] = models_dir
    config["paths"] = paths
    serving = dict(config["serving"])
    model_version = os.environ.get("MODEL_VERSION")
    if model_version:
        serving["model_version"] = model_version
    config["serving"] = serving
    return config


def resolve_model_version(config: dict[str, Any]) -> str:
    """Return the model version folder to load."""
    return str(config["serving"]["model_version"])


class AppState:
    """Holds loaded model artifacts for request handlers."""

    def __init__(
        self,
        config: dict[str, Any],
        pipeline: Any,
        metadata: dict[str, Any],
        model_version: str,
        config_path: Path | str | None,
        request_log: RequestLogWriter,
    ) -> None:
        self.config = config
        self.pipeline = pipeline
        self.metadata = metadata
        self.model_version = model_version
        self.config_path = config_path
        self.request_log = request_log


def _request_log_path() -> Path | None:
    raw = os.environ.get("REQUEST_LOG_PATH")
    if not raw:
        return None
    return Path(raw)


def create_app(
    config_path: Path | str | None = None,
    *,
    pipeline: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> FastAPI:
    """Build the FastAPI application and load the model at startup.

    Args:
        config_path: Optional path to ``config.yaml``.
        pipeline: Optional pre-loaded pipeline for tests.
        metadata: Optional metadata dict when ``pipeline`` is injected.

    Returns:
        Configured FastAPI app.
    """
    config = serving_config(config_path)
    model_version = resolve_model_version(config)
    preloaded = pipeline is not None and metadata is not None
    request_log_writer = RequestLogWriter(_request_log_path())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if preloaded:
            app.state.icu = AppState(
                config,
                pipeline,
                metadata,
                model_version,
                config_path,
                request_log_writer,
            )
        else:
            try:
                loaded_pipeline, loaded_metadata = load_model(
                    model_version,
                    config_path,
                    models_dir=config["paths"]["models_dir"],
                )
            except (FileNotFoundError, ValueError) as exc:
                logger.error("Failed to load model %s: %s", model_version, exc)
                raise SystemExit(1) from exc
            app.state.icu = AppState(
                config,
                loaded_pipeline,
                loaded_metadata,
                model_version,
                config_path,
                request_log_writer,
            )
        yield
        request_log_writer.close()

    app = FastAPI(title="ICU mortality risk API", lifespan=lifespan)

    @app.middleware("http")
    async def log_requests(request: Request, call_next: Any) -> Any:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000.0
        state: AppState = request.app.state.icu
        log_fields = getattr(request.state, "log_fields", None)
        if log_fields is not None:
            record = build_log_record(
                request_id=request_id,
                path=request.url.path,
                status_code=response.status_code,
                latency_ms=latency_ms,
                model_version=log_fields.get("model_version", state.model_version),
                data_quality_status=log_fields.get("data_quality_status"),
                missing_vitals=log_fields.get("missing_vitals"),
                n_measurements_used=log_fields.get("n_measurements_used"),
                n_excluded_after_cutoff=log_fields.get("n_excluded_after_cutoff"),
                n_out_of_range=log_fields.get("n_out_of_range"),
                risk_flag=log_fields.get("risk_flag"),
                feature_bins=log_fields.get("feature_bins"),
                error=log_fields.get("error"),
            )
        else:
            error_type = getattr(request.state, "log_error", None)
            record = build_log_record(
                request_id=request_id,
                path=request.url.path,
                status_code=response.status_code,
                latency_ms=latency_ms,
                model_version=state.model_version if request.url.path != "/docs" else None,
                data_quality_status=None,
                missing_vitals=None,
                n_measurements_used=None,
                n_excluded_after_cutoff=None,
                n_out_of_range=None,
                risk_flag=None,
                feature_bins=None,
                error=error_type,
            )
        state.request_log.write_line(record)
        return response

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        state: AppState = app.state.icu
        return HealthResponse(status="ok", model_version=state.model_version)

    @app.post("/predict", response_model=PredictResponse)
    def predict(body: PredictRequest, request: Request) -> PredictResponse:
        request_id = str(request.state.request_id)
        state: AppState = app.state.icu
        response, feature_bins = predict_from_request(
            body,
            state.config,
            state.pipeline,
            state.metadata,
            request_id,
        )
        dq = response.data_quality
        request.state.log_fields = {
            "model_version": response.model.version,
            "data_quality_status": dq.status,
            "missing_vitals": list(dq.missing_vitals),
            "n_measurements_used": dq.n_measurements_used,
            "n_excluded_after_cutoff": dq.n_excluded_after_cutoff,
            "n_out_of_range": dq.n_out_of_range,
            "risk_flag": response.risk_flag,
            "feature_bins": feature_bins,
        }
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request.state.log_error = "validation_error"
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, RequestValidationError):
            request.state.log_error = "validation_error"
            return await request_validation_exception_handler(request, exc)
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        request.state.log_error = "internal_error"
        logger.exception("Unhandled error for request %s: %s", request_id, exc)
        payload = ErrorResponse(request_id=request_id, error="internal_error")
        return JSONResponse(status_code=500, content=payload.model_dump())

    return app


app = create_app()
