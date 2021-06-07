#
# voice-skill-sdk
#
# (C) 2021, Deutsche Telekom AG
#
# This file is distributed under the terms of the MIT license.
# For details see the file LICENSE in the top directory.
#

import time
from types import SimpleNamespace

import pytest
import respx
import httpx
from httpx import Response

from skill_sdk.middleware.prometheus import (
    Prometheus,
    count_partner_calls,
    handle_metrics,
    partner_call,
    prometheus_latency,
)

from skill_sdk.requests import Client


def test_prometheus_middleware():
    Prometheus.requests_latency()
    Prometheus.partner_requests_count()
    r = SimpleNamespace()
    metrics = handle_metrics(r).body
    assert b"http_requests_latency_seconds" in metrics
    assert b"http_partner_request_count_total" in metrics


def test_prometheus_latency(monkeypatch):
    from skill_sdk.config import settings

    monkeypatch.setattr(settings, "SKILL_NAME", "skill-noname")
    monkeypatch.setattr(settings, "SKILL_VERSION", "1")
    r = SimpleNamespace()

    @prometheus_latency("Latency Test")
    def callback():
        time.sleep(0.025)
        return SimpleNamespace(status_code=200)

    callback()
    metrics = handle_metrics(r).body
    assert (
        b'http_requests_latency_seconds_bucket{job="skill-noname",'
        b'le="0.025",operation="Latency Test",version="1"} 0.0' in metrics
    )

    assert (
        b'http_requests_latency_seconds_bucket{job="skill-noname",'
        b'le="0.05",operation="Latency Test",version="1"} 1.0' in metrics
    )


@respx.mock
def test_prometheus_partner():
    Prometheus.partner_requests_count().clear()

    respx.get("http://fohf_partner_call.com").mock(
        return_value=Response(404, text="resp")
    )
    respx.get("http://working_partner_call.com").mock(
        return_value=Response(200, text="")
    )

    with partner_call("partner-call", httpx.get) as get:
        [get("http://fohf_partner_call.com") for _ in range(0, 15)]
        [get("http://working_partner_call.com") for _ in range(0, 10)]

    metrics = handle_metrics(SimpleNamespace()).body
    assert b'partner_name="partner-call",status="404"} 15.0' in metrics
    assert b'partner_name="partner-call",status="200"} 10.0' in metrics


@respx.mock
def test_partner_call_with_circuit_breaker():
    Prometheus.partner_requests_count().clear()

    respx.get("http://httpbin.org/status/404").mock(
        return_value=Response(404, text="")
    )
    respx.get("http://httpbin.org/status/500").mock(
        return_value=Response(500, text="")
    )

    with Client(response_hook=count_partner_calls("partner-call")) as c404:
        for _ in range(100):
            with pytest.raises(Exception):
                c404.get("http://httpbin.org/status/404")

    with Client(response_hook=count_partner_calls("partner-call")) as c500:
        for _ in range(100):
            with pytest.raises(Exception):
                c500.get("http://httpbin.org/status/500")

    metrics = handle_metrics(SimpleNamespace()).body
    assert (
        b'partner_name="partner-call",status="404"} %d.0'
        % c404.circuit_breaker.fail_max in metrics
    )
    assert (
        b'partner_name="partner-call",status="500"} %d.0'
        % c500.circuit_breaker.fail_max in metrics
    )
