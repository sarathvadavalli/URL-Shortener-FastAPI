import inspect

from myapp.routers.url_router import redirect


def test_redirect_endpoint_is_async():
    assert inspect.iscoroutinefunction(redirect)
