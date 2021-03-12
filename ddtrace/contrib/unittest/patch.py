import unittest
from ddtrace.vendor.wrapt import wrap_function_wrapper as _w
from ddtrace.utils.wrappers import unwrap as _u
from ...utils.formats import get_env
from .test_case import _wrap_test_case_run
from ddtrace import config
from ...pin import Pin
from ...ext import ci

config._add(
    "unittest",
    dict(_default_service="unittest", operation_name=get_env("unittest", "operation_name", default="unittest.test")),
)


def patch():
    if getattr(unittest, "_datadog_patch", False):
        return

    setattr(unittest, "_datadog_patch", True)

    _w("unittest", "TestCase.run", _wrap_test_case_run)
    Pin(app="unittest", _config=config.unittest, tags=ci.tags()).onto(unittest.TestCase)


def unpatch():
    if not getattr(unittest, "_datadog_patch", False):
        return

    setattr(unittest, "_datadog_patch", False)

    _u(unittest.TestCase, "run")
