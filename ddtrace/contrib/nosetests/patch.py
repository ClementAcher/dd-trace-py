import unittest

import nose

from ddtrace.vendor.wrapt import wrap_function_wrapper as _w
from ddtrace.utils.wrappers import unwrap as _u
from ...utils.formats import get_env
from .test_case import _wrap_test_case_run
from ddtrace import config
from ...pin import Pin
from ...ext import ci

config._add(
    "nose",
    dict(_default_service="nose", operation_name=get_env("nose", "operation_name", default="nose.test")),
)


def patch():
    if getattr(nose, "_datadog_patch", False):
        return

    setattr(nose, "_datadog_patch", True)

    _w("nose", "test_case.run", _wrap_test_case_run)
    Pin(app="nose", _config=config.nose, tags=ci.tags()).onto(nose)


def unpatch():
    if not getattr(nose, "_datadog_patch", False):
        return

    setattr(nose, "_datadog_patch", False)

    _u(nose, "run")
