import mock
import pytest

from ddtrace import Pin
from ddtrace import Tracer
from ddtrace import config
from ddtrace.compat import stringify
from ddtrace.contrib import trace_utils
from ddtrace.ext import http
from ddtrace.propagation.http import HTTP_HEADER_PARENT_ID
from ddtrace.propagation.http import HTTP_HEADER_TRACE_ID
from ddtrace.settings import Config
from tests import override_global_config


@pytest.fixture
def int_config():
    c = Config()
    c._add("myint", dict())
    return c


@pytest.fixture
def span(tracer):
    span = tracer.trace(name="myint")
    yield span
    span.finish()


@pytest.mark.parametrize(
    "pin,config_val,default,global_service,expected",
    [
        (Pin(), None, None, None, None),
        (Pin(), None, None, "global-svc", "global-svc"),
        (Pin(), None, "default-svc", None, "default-svc"),
        # Global service should have higher priority than the integration default.
        (Pin(), None, "default-svc", "global-svc", "global-svc"),
        (Pin(), "config-svc", "default-svc", None, "config-svc"),
        (Pin(service="pin-svc"), None, "default-svc", None, "pin-svc"),
        (Pin(service="pin-svc"), "config-svc", "default-svc", None, "pin-svc"),
    ],
)
def test_int_service(int_config, pin, config_val, default, global_service, expected):
    if config_val:
        int_config.myint.service = config_val

    if global_service:
        int_config.service = global_service

    assert trace_utils.int_service(pin, int_config.myint, default) == expected


def test_int_service_integration(int_config):
    pin = Pin()
    tracer = Tracer()
    assert trace_utils.int_service(pin, int_config.myint) is None

    with override_global_config(dict(service="global-svc")):
        assert trace_utils.int_service(pin, int_config.myint) is None

        with tracer.trace("something", service=trace_utils.int_service(pin, int_config.myint)) as s:
            assert s.service == "global-svc"


@pytest.mark.parametrize(
    "pin,config_val,default,expected",
    [
        (Pin(), None, "default-svc", "default-svc"),
        (Pin(), "config-svc", "default-svc", "config-svc"),
        (Pin(service="pin-svc"), None, "default-svc", "pin-svc"),
        (Pin(service="pin-svc"), "config-svc", "default-svc", "pin-svc"),
    ],
)
def test_ext_service(int_config, pin, config_val, default, expected):
    if config_val:
        int_config.myint.service = config_val

    assert trace_utils.ext_service(pin, int_config.myint, default) == expected


@pytest.mark.parametrize(
    "method,url,status_code,status_msg,query,request_headers",
    [
        ("GET", "http://localhost/", 0, None, None, None),
        ("GET", "http://localhost/", 200, "OK", None, None),
        (None, None, None, None, None, None),
        ("GET", "http://localhost/", 200, "OK", None, {"my-header": "value1"}),
        ("GET", "http://localhost/", 200, "OK", "search?q=test+query", {"my-header": "value1"}),
    ],
)
def test_set_http_meta(span, int_config, method, url, status_code, status_msg, query, request_headers):
    int_config.http.trace_headers(["my-header"])
    int_config.trace_query_string = True
    trace_utils.set_http_meta(
        span,
        int_config,
        method=method,
        url=url,
        status_code=status_code,
        status_msg=status_msg,
        query=query,
        request_headers=request_headers,
    )
    if method is not None:
        assert span.meta[http.METHOD] == method
    else:
        assert http.METHOD not in span.meta

    if url is not None:
        assert span.meta[http.URL] == stringify(url)
    else:
        assert http.URL not in span.meta

    if status_code is not None:
        assert span.meta[http.STATUS_CODE] == str(status_code)
        if 500 <= int(status_code) < 600:
            assert span.error == 1
        else:
            assert span.error == 0
    else:
        assert http.STATUS_CODE not in span.meta

    if status_msg is not None:
        assert span.meta[http.STATUS_MSG] == stringify(status_msg)

    if query is not None and int_config.trace_query_string:
        assert span.meta[http.QUERY_STRING] == query

    if request_headers is not None:
        for header, value in request_headers.items():
            tag = "http.request.headers." + header
            assert span.get_tag(tag) == value


@mock.patch("ddtrace.contrib.trace_utils.log")
@pytest.mark.parametrize(
    "error_codes,status_code,error,log_call",
    [
        ("404-400", 400, 1, None),
        ("400-404", 400, 1, None),
        ("400-404", 500, 0, None),
        ("500-520", 530, 0, None),
        ("500-550         ", 530, 1, None),
        ("400-404,419", 419, 1, None),
        ("400,401,403", 401, 1, None),
        ("400-404,X", 0, 0, ("Error status codes was not a number %s", ["X"])),
        ("500-599", 200, 0, None),
    ],
)
def test_set_http_meta_custom_errors(mock_log, span, int_config, error_codes, status_code, error, log_call):
    config.http_server.error_statuses = error_codes
    trace_utils.set_http_meta(span, int_config, status_code=status_code)
    assert span.error == error
    if log_call:
        mock_log.exception.assert_called_once_with(*log_call)
    else:
        mock_log.exception.assert_not_called()


def test_activate_distributed_headers_enabled(int_config):
    tracer = Tracer()
    int_config.myint["distributed_tracing_enabled"] = True
    headers = {
        HTTP_HEADER_PARENT_ID: "12345",
        HTTP_HEADER_TRACE_ID: "678910",
    }
    trace_utils.activate_distributed_headers(tracer, int_config.myint, headers)
    context = tracer.context_provider.active()

    assert context.trace_id == 678910
    assert context.span_id == 12345


def test_activate_distributed_headers_disabled(int_config):
    tracer = Tracer()
    int_config.myint["distributed_tracing_enabled"] = False
    headers = {
        HTTP_HEADER_PARENT_ID: "12345",
        HTTP_HEADER_TRACE_ID: "678910",
    }
    trace_utils.activate_distributed_headers(tracer, int_config.myint, headers)
    context = tracer.context_provider.active()

    assert context.trace_id is None
    assert context.span_id is None


def test_activate_distributed_headers_no_headers(int_config):
    tracer = Tracer()
    int_config.myint["distributed_tracing_enabled"] = True

    trace_utils.activate_distributed_headers(tracer, int_config.myint, request_headers=None)
    context = tracer.context_provider.active()

    assert context.trace_id is None
    assert context.span_id is None
