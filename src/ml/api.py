"""Minimal FastAPI service for occupancy predictions."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from .predict import OccupancyPredictor


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.predictor = OccupancyPredictor()
        app.state.model_error = None
    except (FileNotFoundError, ValueError) as exc:
        app.state.predictor = None
        app.state.model_error = str(exc)
    yield


app = FastAPI(title="GDG Campus Occupancy API", lifespan=lifespan)
origins = [item.strip() for item in os.getenv(
    "OCCUPANCY_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
).split(",") if item.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"],
                   allow_headers=["*"], allow_credentials=True)


def predictor(request: Request) -> OccupancyPredictor:
    if request.app.state.predictor is None:
        raise HTTPException(status_code=503, detail=request.app.state.model_error)
    return request.app.state.predictor


@app.get("/api/predict")
def predict(request: Request, building: str, weekday: str, time: str,
            week: int = Query(ge=1, le=15)):
    try:
        return predictor(request).predict_occupancy(building, weekday, time, week)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/predict/campus")
def predict_all(request: Request, weekday: str, time: str,
                week: int = Query(ge=1, le=15)):
    try:
        return predictor(request).predict_campus(weekday, time, week)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
