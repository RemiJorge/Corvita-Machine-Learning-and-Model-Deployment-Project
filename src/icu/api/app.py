"""FastAPI routes, middleware, and application factory."""

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
    ) -> None:
        self.config = config
        self.pipeline = pipeline
        self.metadata = metadata
        self.model_version = model_version
        self.config_path = config_path


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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if preloaded:
            app.state.icu = AppState(config, pipeline, metadata, model_version, config_path)
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
            )
        yield

    app = FastAPI(title="ICU mortality risk API", lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        state: AppState = app.state.icu
        return HealthResponse(status="ok", model_version=state.model_version)

    @app.post("/predict", response_model=PredictResponse)
    def predict(body: PredictRequest, request: Request) -> PredictResponse:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        state: AppState = app.state.icu
        return predict_from_request(
            body,
            state.config,
            state.pipeline,
            state.metadata,
            request_id,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.exception("Unhandled error for request %s: %s", request_id, exc)
        payload = ErrorResponse(request_id=request_id, error="internal_error")
        return JSONResponse(status_code=500, content=payload.model_dump())

    return app


app = create_app()
