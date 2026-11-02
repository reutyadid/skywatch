"""Backend tests. Open-Meteo is mocked, so they need no network."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app import app

GEOCODING_OK = {
    "results": [
        {"name": "Haifa", "country": "Israel", "latitude": 32.81, "longitude": 34.99},
    ]
}
FORECAST_OK = {"current": {"temperature_2m": 18.8, "weather_code": 3}}


def open_meteo_answer(body, status_error=None):
    """Build a fake requests.Response."""
    response = MagicMock()
    response.json.return_value = body
    response.raise_for_status.side_effect = status_error
    return response


@pytest.fixture
def client():
    return app.test_client()


@pytest.fixture
def mock_get():
    with patch("app.requests.get") as mocked:
        yield mocked


def test_weather_returns_current_conditions(client, mock_get):
    mock_get.side_effect = [open_meteo_answer(GEOCODING_OK), open_meteo_answer(FORECAST_OK)]

    response = client.get("/api/weather?city=Haifa")

    assert response.status_code == 200
    assert response.get_json() == {
        "city": "Haifa",
        "country": "Israel",
        "temperature_c": 18.8,
        "conditions": "Overcast",
    }


def test_unlisted_weather_code_is_unknown(client, mock_get):
    forecast = {"current": {"temperature_2m": 18.8, "weather_code": 1000}}
    mock_get.side_effect = [open_meteo_answer(GEOCODING_OK), open_meteo_answer(forecast)]

    response = client.get("/api/weather?city=Haifa")

    assert response.get_json()["conditions"] == "Unknown"


@pytest.mark.parametrize("url", ["/api/weather", "/api/weather?city=", "/api/weather?city=%20"])
def test_missing_city_returns_400(client, mock_get, url):
    response = client.get(url)

    assert response.status_code == 400
    assert "error" in response.get_json()
    mock_get.assert_not_called()


def test_unknown_city_returns_404(client, mock_get):
    # The real API leaves out "results" when nothing matches.
    mock_get.return_value = open_meteo_answer({"generationtime_ms": 0.1})

    response = client.get("/api/weather?city=Nowherexyzq")

    assert response.status_code == 404
    assert "error" in response.get_json()


def test_upstream_http_error_returns_502(client, mock_get):
    mock_get.return_value = open_meteo_answer({}, status_error=requests.HTTPError("500"))

    response = client.get("/api/weather?city=Haifa")

    assert response.status_code == 502


def test_upstream_connection_error_returns_502(client, mock_get):
    mock_get.side_effect = requests.ConnectionError("refused")

    response = client.get("/api/weather?city=Haifa")

    assert response.status_code == 502


@pytest.mark.parametrize("geocoding", [[], {"results": [{"name": "Haifa"}]}, {"results": "x"}])
def test_unexpected_geocoding_response_returns_502(client, mock_get, geocoding):
    mock_get.return_value = open_meteo_answer(geocoding)

    response = client.get("/api/weather?city=Haifa")

    # [] has no "results" to read: it must not be mistaken for an unknown city.
    assert response.status_code == 502


def test_unexpected_forecast_response_returns_502(client, mock_get):
    mock_get.side_effect = [open_meteo_answer(GEOCODING_OK), open_meteo_answer({"current": {}})]

    response = client.get("/api/weather?city=Haifa")

    assert response.status_code == 502


def test_geocoding_timeout_returns_504(client, mock_get):
    mock_get.side_effect = requests.Timeout()

    response = client.get("/api/weather?city=Haifa")

    assert response.status_code == 504


def test_forecast_timeout_returns_504(client, mock_get):
    mock_get.side_effect = [open_meteo_answer(GEOCODING_OK), requests.Timeout()]

    response = client.get("/api/weather?city=Haifa")

    assert response.status_code == 504


def test_healthz_makes_no_external_calls(client, mock_get):
    response = client.get("/healthz")

    assert response.status_code == 200
    mock_get.assert_not_called()


def test_metrics_show_requests_and_upstream_errors(client, mock_get):
    mock_get.side_effect = requests.Timeout()
    client.get("/api/weather?city=Haifa")

    body = client.get("/metrics").get_data(as_text=True)

    assert 'http_requests_total{handler="weather",method="GET",status="504"}' in body
    assert 'http_request_duration_seconds_count{handler="weather"}' in body
    assert 'upstream_request_duration_seconds_count{api="geocoding"}' in body
    assert 'upstream_errors_total{api="geocoding"}' in body


def test_probes_and_scrapes_are_not_counted(client):
    client.get("/healthz")

    body = client.get("/metrics").get_data(as_text=True)

    assert 'handler="healthz"' not in body
    assert 'handler="metrics"' not in body
