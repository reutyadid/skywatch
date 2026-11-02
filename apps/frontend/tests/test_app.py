"""Frontend tests. The backend is mocked, so they need no network."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from app import BACKEND_TIMEOUT_SECONDS, BACKEND_URL, app

WEATHER_OK = {
    "city": "Haifa",
    "country": "Israel",
    "temperature_c": 18.8,
    "conditions": "Overcast",
}


def backend_answer(status_code, body=None, status_error=None):
    """Build a fake requests.Response."""
    response = MagicMock()
    response.status_code = status_code
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


@pytest.mark.parametrize("url", ["/", "/?city=", "/?city=%20"])
def test_no_city_shows_only_the_form(client, mock_get, url):
    response = client.get(url)

    assert response.status_code == 200
    assert '<input type="text" name="city"' in response.get_data(as_text=True)
    mock_get.assert_not_called()


def test_shows_temperature_and_conditions(client, mock_get):
    mock_get.return_value = backend_answer(200, WEATHER_OK)

    response = client.get("/?city=Haifa")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Haifa, Israel" in page
    assert "18.8 °C" in page
    assert "Overcast" in page


def test_calls_the_configured_backend_url_with_the_timeout(client, mock_get):
    mock_get.return_value = backend_answer(200, WEATHER_OK)

    client.get("/?city=Haifa")

    mock_get.assert_called_once_with(
        f"{BACKEND_URL}/api/weather",
        params={"city": "Haifa"},
        timeout=BACKEND_TIMEOUT_SECONDS,
    )


def test_unknown_city_shows_message(client, mock_get):
    mock_get.return_value = backend_answer(404)

    response = client.get("/?city=Nowherexyzq")

    assert response.status_code == 404
    assert "City not found: Nowherexyzq" in response.get_data(as_text=True)


def test_backend_timeout_shows_message(client, mock_get):
    mock_get.side_effect = requests.Timeout()

    response = client.get("/?city=Haifa")

    assert response.status_code == 504
    assert "took too long" in response.get_data(as_text=True)


def test_backend_down_shows_message(client, mock_get):
    mock_get.side_effect = requests.ConnectionError("refused")

    response = client.get("/?city=Haifa")

    assert response.status_code == 502
    assert "unavailable" in response.get_data(as_text=True)


@pytest.mark.parametrize("status_code", [502, 504])
def test_backend_error_status_shows_message(client, mock_get, status_code):
    mock_get.return_value = backend_answer(status_code, status_error=requests.HTTPError())

    response = client.get("/?city=Haifa")

    assert response.status_code == 502
    assert "unavailable" in response.get_data(as_text=True)


def test_city_with_html_is_escaped(client, mock_get):
    mock_get.return_value = backend_answer(404)

    response = client.get("/?city=<script>alert(1)</script>")

    page = response.get_data(as_text=True)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_healthz_makes_no_backend_call(client, mock_get):
    response = client.get("/healthz")

    assert response.status_code == 200
    mock_get.assert_not_called()


def test_metrics_show_requests_and_upstream_errors(client, mock_get):
    mock_get.side_effect = requests.Timeout()
    client.get("/?city=Haifa")

    body = client.get("/metrics").get_data(as_text=True)

    assert 'http_requests_total{handler="index",method="GET",status="504"}' in body
    assert 'http_request_duration_seconds_count{handler="index"}' in body
    assert 'upstream_request_duration_seconds_count{api="backend"}' in body
    assert 'upstream_errors_total{api="backend"}' in body


def test_unknown_city_is_not_an_upstream_error(client, mock_get):
    before = client.get("/metrics").get_data(as_text=True)
    mock_get.return_value = backend_answer(404)

    client.get("/?city=Nowherexyzq")

    after = client.get("/metrics").get_data(as_text=True)
    errors_before = [line for line in before.splitlines() if line.startswith("upstream_errors")]
    errors_after = [line for line in after.splitlines() if line.startswith("upstream_errors")]
    assert errors_before == errors_after


def test_probes_and_scrapes_are_not_counted(client):
    client.get("/healthz")

    body = client.get("/metrics").get_data(as_text=True)

    assert 'handler="healthz"' not in body
    assert 'handler="metrics"' not in body
