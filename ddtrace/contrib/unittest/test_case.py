import logging
from six import PY2
import unittest
from ddtrace.vendor.wrapt import ObjectProxy

from ..pytest.constants import FRAMEWORK, KIND
from ...ext import SpanTypes
from ...pin import Pin
from ddtrace import config
from ...ext import SpanTypes
from ...constants import SPAN_KIND
from ..trace_utils import int_service
from ...ext import test as ddtest

log = logging.Logger(__name__)


class TestResultProxy(ObjectProxy):
    def __init__(self, wrapped, span):
        super(TestResultProxy, self).__init__(wrapped)
        self._span = span

    def addError(self, test, err):
        self._span.set_exc_info(*err)
        self._span.set_tag(ddtest.STATUS, ddtest.Status.FAIL.value)
        return self.__wrapped__.addError(test, err)

    def addFailure(self, test, err):
        self._span.set_tag(ddtest.STATUS, ddtest.Status.FAIL.value)
        self._span.set_exc_info(*err)
        return self.__wrapped__.addFailure(test, err)

    def addSuccess(self, test):
        self._span.set_tag(ddtest.STATUS, ddtest.Status.PASS.value)
        return self.__wrapped__.addSuccess(test)

    def addSkip(self, test, reason):
        self._span.set_tag(ddtest.STATUS, ddtest.Status.SKIP.value)
        if reason is not None:
            self._span.set_tag(ddtest.SKIP_REASON, reason)
        return self.__wrapped__.addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        etype, value, tb = err
        return self.__wrapped__.addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        return self.__wrapped__.addUnexpectedSuccess(test)


def _run_test(wrapped, instance, result):
    if PY2:
        name = instance.__class__.__name__
    else:
        name = instance.__class__.__qualname__

    test_suite = "%s.%s" % (instance.__class__.__module__, name)
    test_name = instance._testMethodName
    fqn = "%s.%s" % (test_suite, test_name)

    pin = Pin.get_from(unittest.TestCase)
    if pin is None:
        return wrapped(result)

    with pin.tracer.trace(
        config.unittest.operation_name,
        service=int_service(pin, config.unittest),
        resource=fqn,
        span_type=SpanTypes.TEST.value,
    ) as span:
        span.set_tags(pin.tags)
        span.set_tag(SPAN_KIND, KIND)
        span.set_tag(ddtest.FRAMEWORK, FRAMEWORK)
        span.set_tag(ddtest.NAME, test_name)
        span.set_tag(ddtest.SUITE, test_suite)
        span.set_tag(ddtest.TYPE, SpanTypes.TEST.value)
        return wrapped(TestResultProxy(result, span))


def _wrap_test_case_run(func, instance, args, kwargs):
    log.debug("intercepting test: instance=%s args=%s kwargs=%s", instance, args, kwargs)
    # result argument to UnitTest.run() is optional. If not given, default is created.
    if args:
        result = args[0]
    elif "result" in kwargs:
        result = kwargs["result"]
    else:
        result = instance.defaultTestResult()
    return _run_test(func, instance, result)
