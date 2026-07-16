"""A small application that can be used to test a WSGI server and check
it for WSGI compliance.
"""

from __future__ import annotations

import importlib.metadata
import os
import sys
import typing as t
from textwrap import wrap

from markupsafe import escape

from .wrappers.request import Request
from .wrappers.response import Response

TEMPLATE = """\
<!doctype html>
<html lang=en>
<title>WSGI Information</title>
<style type="text/css">
  @import url(https://fonts.googleapis.com/css?family=Ubuntu);

  body       { font-family: 'Lucida Grande', 'Lucida Sans Unicode', 'Geneva',
               'Verdana', sans-serif; background-color: white; color: #000;
               font-size: 15px; text-align: center; }
  div.box    { text-align: left; width: 45em; margin: auto; padding: 50px 0;
               background-color: white; }
  h1, h2     { font-family: 'Ubuntu', 'Lucida Grande', 'Lucida Sans Unicode',
               'Geneva', 'Verdana', sans-serif; font-weight: normal; }
  h1         { margin: 0 0 30px 0; }
  h2         { font-size: 1.4em; margin: 1em 0 0.5em 0; }
  table      { width: 100%%; border-collapse: collapse; border: 1px solid #AFC5C9 }
  table th   { background-color: #AFC1C4; color: white; font-size: 0.72em;
               font-weight: normal; width: 18em; vertical-align: top;
               padding: 0.5em 0 0.1em 0.5em; }
  table td   { border: 1px solid #AFC5C9; padding: 0.1em 0 0.1em 0.5em; }
  code       { font-family: 'Consolas', 'Monaco', 'Bitstream Vera Sans Mono',
               monospace; font-size: 0.7em; }
  ul li      { line-height: 1.5em; }
  ul.path    { font-size: 0.7em; margin: 0 -30px; padding: 8px 30px;
               list-style: none; background: #E8EFF0; }
  ul.path li { line-height: 1.6em; }
  li.virtual { color: #999; text-decoration: underline; }
  li.exp     { background: white; }
</style>
<div class="box">
  <h1>WSGI Information</h1>
  <p>
    This page displays all available information about the WSGI server and
    the underlying Python interpreter.
  <h2 id="python-interpreter">Python Interpreter</h2>
  <table>
    <tr>
      <th>Python Version
      <td>%(python_version)s
    <tr>
      <th>Platform
      <td>%(platform)s [%(os)s]
    <tr>
      <th>API Version
      <td>%(api_version)s
    <tr>
      <th>Byteorder
      <td>%(byteorder)s
    <tr>
      <th>Werkzeug Version
      <td>%(werkzeug_version)s
  </table>
  <h2 id="wsgi-environment">WSGI Environment</h2>
  <table>%(wsgi_env)s</table>
  <h2 id="installed-eggs">Installed Eggs</h2>
  <p>
    The following python packages were installed on the system as
    Python eggs:
  <ul>%(python_eggs)s</ul>
  <h2 id="sys-path">System Path</h2>
  <p>
    The following paths are the current contents of the load path.  The
    following entries are looked up for Python packages.  Note that not
    all items in this path are folders.  Gray and underlined items are
    entries pointing to invalid resources or used by custom import hooks
    such as the zip importer.
  <p>
    Items with a bright background were expanded for display from a relative
    path.  If you encounter such paths in the output you might want to check
    your setup as relative paths are usually problematic in multithreaded
    environments.
  <ul class="path">%(sys_path)s</ul>
</div>
"""


def iter_sys_path() -> t.Iterator[tuple[str, bool, bool]]:
    if os.name == "posix":

        def strip(x: str) -> str:
            prefix = os.path.expanduser("~")
            if x.startswith(prefix):
                x = f"~{x[len(prefix) :]}"
            return x

    else:

        def strip(x: str) -> str:
            return x

    cwd = os.path.abspath(os.getcwd())
    for item in sys.path:
        path = os.path.join(cwd, item or os.path.curdir)
        yield strip(os.path.normpath(path)), not os.path.isdir(path), path != item


@Request.application
def test_app(req: Request) -> Response:
    """Simple test application that dumps the environment.  You can use
    it to check if Werkzeug is working properly:

    .. sourcecode:: pycon

        >>> from werkzeug.serving import run_simple
        >>> from werkzeug.testapp import test_app
        >>> run_simple('localhost', 3000, test_app)
         * Running on http://localhost:3000/

    The application displays important information from the WSGI environment,
    the Python interpreter and the installed libraries.
    """
    try:
        import pkg_resources
    except ImportError:
        eggs: t.Iterable[t.Any] = ()
    else:
        eggs = sorted(
            pkg_resources.working_set,
            key=lambda x: x.project_name.lower(),
        )
    python_eggs = []
    for egg in eggs:
        try:
            version = egg.version
        except (ValueError, AttributeError):
            version = "unknown"
        python_eggs.append(
            f"<li>{escape(egg.project_name)} <small>[{escape(version)}]</small>"
        )

    wsgi_env = []
    sorted_environ = sorted(req.environ.items(), key=lambda x: repr(x[0]).lower())
    for key, value in sorted_environ:
        value = "".join(wrap(str(escape(repr(value)))))
        wsgi_env.append(f"<tr><th>{escape(key)}<td><code>{value}</code>")

    sys_path = []
    for item, virtual, expanded in iter_sys_path():
        css = []
        if virtual:
            css.append("virtual")
        if expanded:
            css.append("exp")
        class_str = f' class="{" ".join(css)}"' if css else ""
        sys_path.append(f"<li{class_str}>{escape(item)}")

    context = {
        "python_version": "<br>".join(escape(sys.version).splitlines()),
        "platform": escape(sys.platform),
        "os": escape(os.name),
        "api_version": sys.api_version,
        "byteorder": sys.byteorder,
        "werkzeug_version": _get_werkzeug_version(),
        "python_eggs": "\n".join(python_eggs),
        "wsgi_env": "\n".join(wsgi_env),
        "sys_path": "\n".join(sys_path),
    }
    return Response(TEMPLATE % context, mimetype="text/html")


_werkzeug_version = ""


def _get_werkzeug_version() -> str:
    global _werkzeug_version

    if not _werkzeug_version:
        _werkzeug_version = importlib.metadata.version("werkzeug")

    return _werkzeug_version


if __name__ == "__main__":
    from .serving import run_simple

    run_simple("localhost", 5000, test_app, use_reloader=True)
