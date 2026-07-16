from __future__ import annotations

import typing as t

from . import typing as ft
from .globals import current_app
from .globals import request

F = t.TypeVar("F", bound=t.Callable[..., t.Any])

http_method_funcs = frozenset(
    ["get", "post", "head", "options", "delete", "put", "trace", "patch"]
)


class View:
    """Subclass this class and override :meth:`dispatch_request` to
    create a generic class-based view. Call :meth:`as_view` to create a
    view function that creates an instance of the class with the given
    arguments and calls its ``dispatch_request`` method with any URL
    variables.

    See :doc:`views` for a detailed guide.

    .. code-block:: python

        class Hello(View):
            init_every_request = False

            def dispatch_request(self, name):
                return f"Hello, {name}!"

        app.add_url_rule(
            "/hello/<name>", view_func=Hello.as_view("hello")
        )

    Set :attr:`methods` on the class to change what methods the view
    accepts.

    Set :attr:`decorators` on the class to apply a list of decorators to
    the generated view function. Decorators applied to the class itself
    will not be applied to the generated view function!

    Set :attr:`init_every_request` to ``False`` for efficiency, unless
    you need to store request-global data on ``self``.
    """

    #: The methods this view is registered for. Uses the same default
    #: (``["GET", "HEAD", "OPTIONS"]``) as ``route`` and
    #: ``add_url_rule`` by default.
    methods: t.ClassVar[t.Collection[str] | None] = None

    #: Control whether the ``OPTIONS`` method is handled automatically.
    #: Uses the same default (``True``) as ``route`` and
    #: ``add_url_rule`` by default.
    provide_automatic_options: t.ClassVar[bool | None] = None

    #: A list of decorators to apply, in order, to the generated view
    #: function. Remember that ``@decorator`` syntax is applied bottom
    #: to top, so the first decorator in the list would be the bottom
    #: decorator.
    #:
    #: .. versionadded:: 0.8
    decorators: t.ClassVar[list[t.Callable[..., t.Any]]] = []

    #: Create a new instance of this view class for every request by
    #: default. If a view subclass sets this to ``False``, the same
    #: instance is used for every request.
    #:
    #: A single instance is more efficient, especially if complex setup
    #: is done during init. However, storing data on ``self`` is no
    #: longer safe across requests, and :data:`~flask.g` should be used
    #: instead.
    #:
    #: .. versionadded:: 2.2
    init_every_request: t.ClassVar[bool] = True

    def dispatch_request(self) -> ft.ResponseReturnValue:
        """The actual view function behavior. Subclasses must override
        this and return a valid response. Any variables from the URL
        rule are passed as keyword arguments.
        """
        raise NotImplementedError()

    @classmethod
    def as_view(
        cls, name: str, *class_args: t.Any, **class_kwargs: t.Any
    ) -> ft.RouteCallable:
        """Convert the class into a view function that can be registered
        for a route.

        By default, the generated view will create a new instance of the
        view class for every request and call its
        :meth:`dispatch_request` method. If the view class sets
        :attr:`init_every_request` to ``False``, the same instance will
        be used for every request.

        Except for ``name``, all other arguments passed to this method
        are forwarded to the view class ``__init__`` method.

        .. versionchanged:: 2.2
            Added the ``init_every_request`` class attribute.
        """
        if cls.init_every_request:

            def view(**kwargs: t.Any) -> ft.ResponseReturnValue:
                self = view.view_class(  # type: ignore[attr-defined]
                    *class_args, **class_kwargs
                )
                return current_app.ensure_sync(self.dispatch_request)(**kwargs)  # type: ignore[no-any-return]

        else:
            self = cls(*class_args, **class_kwargs)  # pyright: ignore

            def view(**kwargs: t.Any) -> ft.ResponseReturnValue:
                return current_app.ensure_sync(self.dispatch_request)(**kwargs)  # type: ignore[no-any-return]

        if cls.decorators:
            view.__name__ = name
            view.__module__ = cls.__module__
            for decorator in cls.decorators:
                view = decorator(view)

        # We attach the view class to the view function for two reasons:
        # first of all it allows us to easily figure out what class-based
        # view this thing came from, secondly it's also used for instantiating
        # the view class so you can actually replace it with something else
        # for testing purposes and debugging.
        view.view_class = cls  # type: ignore
        view.__name__ = name
        view.__doc__ = cls.__doc__
        view.__module__ = cls.__module__
        view.methods = cls.methods  # type: ignore
        view.provide_automatic_options = cls.provide_automatic_options  # type: ignore
        return view


class MethodView(View):
    """Dispatches request methods to the corresponding instance methods.
    For example, if you implement a ``get`` method, it will be used to
    handle ``GET`` requests.

    This can be useful for defining a REST API.

    :attr:`methods` is automatically set based on the methods defined on
    the class.

    See :doc:`views` for a detailed guide.

    .. code-block:: python

        class CounterAPI(MethodView):
            def get(self):
                return str(session.get("counter", 0))

            def post(self):
                session["counter"] = session.get("counter", 0) + 1
                return redirect(url_for("counter"))

        app.add_url_rule(
            "/counter", view_func=CounterAPI.as_view("counter")
        )
    """

    def __init_subclass__(cls, **kwargs: t.Any) -> None:
        super().__init_subclass__(**kwargs)

        if "methods" not in cls.__dict__:
            methods = set()

            for base in cls.__bases__:
                if getattr(base, "methods", None):
                    methods.update(base.methods)  # type: ignore[attr-defined]

            for key in http_method_funcs:
                if hasattr(cls, key):
                    methods.add(key.upper())

            if methods:
                cls.methods = methods

    def dispatch_request(self, **kwargs: t.Any) -> ft.ResponseReturnValue:
        meth = getattr(self, request.method.lower(), None)

        # If the request method is HEAD and we don't have a handler for it
        # retry with GET.
        if meth is None and request.method == "HEAD":
            meth = getattr(self, "get", None)

        assert meth is not None, f"Unimplemented method {request.method!r}"
        return current_app.ensure_sync(meth)(**kwargs)  # type: ignore[no-any-return]
