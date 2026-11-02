"""SkyWatch frontend: a city form that shows the current weather from the backend."""

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime

import requests
from flask import Flask, g, jsonify, render_template, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# --- Configuration (all from environment variables) ---

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_TIMEOUT_SECONDS = float(os.getenv("BACKEND_TIMEOUT_SECONDS", "10"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Probes and scrapes are left out of logs and metrics, so they don't drown out real traffic.
UNMEASURED_ENDPOINTS = {"healthz", "metrics"}

# --- Logging: one JSON object per line on stdout ---


class JsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        entry.update(getattr(record, "fields", {}))
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


log_handler = logging.StreamHandler(sys.stdout)
log_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=LOG_LEVEL, handlers=[log_handler])

# --- Metrics (same names as the backend, so one dashboard shows both services) ---

# "handler", not "endpoint": Prometheus Operator adds its own "endpoint" label to every series.
REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "handler", "status"])
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration", ["handler"]
)
UPSTREAM_DURATION = Histogram(
    "upstream_request_duration_seconds", "Backend request duration", ["api"]
)
UPSTREAM_ERRORS = Counter("upstream_errors_total", "Backend request errors", ["api"])

app = Flask(__name__)


@app.before_request
def start_timer():
    g.start_time = time.perf_counter()


@app.after_request
def record_request(response):
    if request.endpoint in UNMEASURED_ENDPOINTS:
        return response

    duration = time.perf_counter() - g.start_time
    # Unknown URLs share one label, so random paths can't create endless metric series.
    handler = request.endpoint or "unmatched"
    REQUESTS.labels(request.method, handler, response.status_code).inc()
    REQUEST_DURATION.labels(handler).observe(duration)
    app.logger.info(
        "request",
        extra={
            "fields": {
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 1),
            }
        },
    )
    return response


# --- Backend ---


class CityNotFound(Exception):
    """The backend does not know this city."""


class BackendError(Exception):
    """The backend is down, or returned an error or a response we can't read."""


class BackendTimeout(Exception):
    """The backend did not answer in time."""


def fetch_weather(city):
    start = time.perf_counter()
    try:
        response = requests.get(
            f"{BACKEND_URL}/api/weather",
            params={"city": city},
            timeout=BACKEND_TIMEOUT_SECONDS,
        )
        # A 404 is a normal answer about the city, not a backend failure.
        if response.status_code == 404:
            raise CityNotFound
        response.raise_for_status()
        return response.json()
    except requests.Timeout as error:
        UPSTREAM_ERRORS.labels("backend").inc()
        app.logger.warning("Backend timed out")
        raise BackendTimeout from error
    except requests.RequestException as error:
        UPSTREAM_ERRORS.labels("backend").inc()
        app.logger.warning("Backend call failed")
        raise BackendError from error
    finally:
        UPSTREAM_DURATION.labels("backend").observe(time.perf_counter() - start)


# --- Routes ---


@app.get("/")
def index():
    city = request.args.get("city", "").strip()
    if not city:
        return render_template("index.html")

    try:
        weather = fetch_weather(city)
    except CityNotFound:
        return render_template("index.html", city=city, error=f"City not found: {city}"), 404
    except BackendTimeout:
        error = "The weather service took too long"
        return render_template("index.html", city=city, error=error), 504
    except BackendError:
        error = "The weather service is unavailable"
        return render_template("index.html", city=city, error=error), 502

    return render_template("index.html", city=city, weather=weather)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
