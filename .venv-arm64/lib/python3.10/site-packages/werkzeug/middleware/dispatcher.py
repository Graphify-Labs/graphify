"""
Application Dispatcher
======================

This middleware creates a single WSGI application that dispatches to
multiple other WSGI applications mounted at different URL paths.

A common example is writing a Single Page Application, where you have a
backend API and a frontend written in JavaScript that does the routing
in the browser rather than requesting different pages from the server.
The frontend is a single HTML and JS file that should be served for any
path besides "/api".

This example dispatches to an API app under "/api", an admin app
under "/admin", and an app that serves frontend files for all other
requests::

    app = DispatcherMiddleware(serve_frontend, {
        '/api': api_app,
        '/admin': admin_app,
    })

In production, you might instead handle this at the HTTP server level,
serving files or proxying to application servers based on location. The
API and admin apps would each be deployed with a separate WSGI server,
and the static files would be served directly by the HTTP server.

.. autoclass:: DispatcherMiddleware

:copyright: 2007 Pallets
:license: BSD-3-Clause
"""

from __future__ import annotations

import typing as t

if t.TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse
    from _typeshed.wsgi import WSGIApplication
    from _typeshed.wsgi import WSGIEnvironment


class DispatcherMiddleware:
    """Combine multiple applications as a single WSGI application.
    Requests are dispatched to an application based on the path it is
    mounted under.

    :param app: The WSGI application to dispatch to if the request
        doesn't match a mounted path.
    :param mounts: Maps path prefixes to applications for dispatching.
    """

    def __init__(
        self,
        app: WSGIApplication,
        mounts: dict[str, WSGIApplication] | None = None,
    ) -> None:
        self.app = app
        self.mounts = mounts or {}

    def __call__(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> t.Iterable[bytes]:
        script = environ.get("PATH_INFO", "")
        path_info = ""

        while "/" in script:
            if script in self.mounts:
                app = self.mounts[script]
                break

            script, last_item = script.rsplit("/", 1)
            path_info = f"/{last_item}{path_info}"
        else:
            app = self.mounts.get(script, self.app)

        original_script_name = environ.get("SCRIPT_NAME", "")
        environ["SCRIPT_NAME"] = original_script_name + script
        environ["PATH_INFO"] = path_info
        return app(environ, start_response)
