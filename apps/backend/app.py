"""SkyWatch backend: takes a city and returns its current weather from Open-Meteo."""

import json
import logging
import os
import sys
import time
from datetime import UTC, datetime

import requests
from flask import Flask, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# --- Configuration (all from environment variables) ---

GEOCODING_URL = os.getenv(
    "OPEN_METEO_GEOCODING_URL", "https://geocoding-api.open-meteo.com/v1/search"
)
FORECAST_URL = os.getenv("OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast")
TIMEOUT_SECONDS = float(os.getenv("OPEN_METEO_TIMEOUT_SECONDS", "5"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Open-Meteo reports conditions as WMO weather codes.
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Light freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Showers",
    82: "Heavy showers",
    85: "Light snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with light hail",
    99: "Thunderstorm with hail",
}

# Raised when Open-Meteo answers with JSON of an unexpected shape.
BAD_RESPONSE_ERRORS = (AttributeError, KeyError, TypeError)

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

# --- Metrics ---

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "endpoint", "status"])
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds", "HTTP request duration", ["endpoint"]
)
UPSTREAM_DURATION = Histogram(
    "upstream_request_duration_seconds", "Open-Meteo request duration", ["api"]
)
UPSTREAM_ERRORS = Counter("upstream_errors_total", "Open-Meteo request errors", ["api"])

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
    endpoint = request.endpoint or "unmatched"
    REQUESTS.labels(request.method, endpoint, response.status_code).inc()
    REQUEST_DURATION.labels(endpoint).observe(duration)
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


# --- Open-Meteo ---


class UpstreamError(Exception):
    """Open-Meteo returned an error or a response we can't read."""


class UpstreamTimeout(Exception):
    """Open-Meteo did not answer in time."""


def call_open_meteo(api, url, params):
    start = time.perf_counter()
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.Timeout as error:
        UPSTREAM_ERRORS.labels(api).inc()
        raise UpstreamTimeout(f"Open-Meteo {api} timed out") from error
    except requests.RequestException as error:
        UPSTREAM_ERRORS.labels(api).inc()
        raise UpstreamError(f"Open-Meteo {api} failed") from error
    finally:
        UPSTREAM_DURATION.labels(api).observe(time.perf_counter() - start)


def find_city(name):
    """Return the best match for a city name, or None if there is no match."""
    data = call_open_meteo("geocoding", GEOCODING_URL, {"name": name, "count": 1})
    try:
        # Open-Meteo leaves out "results" entirely when nothing matches.
        results = data.get("results")
        if not results:
            return None
        place = results[0]
        return {
            "name": place["name"],
            "country": place.get("country", ""),
            "latitude": place["latitude"],
            "longitude": place["longitude"],
        }
    except BAD_RESPONSE_ERRORS as error:
        UPSTREAM_ERRORS.labels("geocoding").inc()
        raise UpstreamError("Open-Meteo geocoding returned an unexpected response") from error


def get_current_weather(latitude, longitude):
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code",
    }
    data = call_open_meteo("forecast", FORECAST_URL, params)
    try:
        current = data["current"]
        return {
            "temperature_c": current["temperature_2m"],
            "conditions": WEATHER_CODES.get(current["weather_code"], "Unknown"),
        }
    except BAD_RESPONSE_ERRORS as error:
        UPSTREAM_ERRORS.labels("forecast").inc()
        raise UpstreamError("Open-Meteo forecast returned an unexpected response") from error


# --- Routes ---


@app.errorhandler(UpstreamError)
def handle_upstream_error(error):
    app.logger.warning(str(error))
    return jsonify(error=str(error)), 502


@app.errorhandler(UpstreamTimeout)
def handle_upstream_timeout(error):
    app.logger.warning(str(error))
    return jsonify(error=str(error)), 504


@app.get("/api/weather")
def weather():
    city = request.args.get("city", "").strip()
    if not city:
        return jsonify(error="Query parameter 'city' is required"), 400

    place = find_city(city)
    if place is None:
        return jsonify(error=f"City not found: {city}"), 404

    current = get_current_weather(place["latitude"], place["longitude"])
    return jsonify(city=place["name"], country=place["country"], **current)


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.get("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
