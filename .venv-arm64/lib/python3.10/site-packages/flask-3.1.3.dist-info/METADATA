Metadata-Version: 2.4
Name: Flask
Version: 3.1.3
Summary: A simple framework for building complex web applications.
Maintainer-email: Pallets <contact@palletsprojects.com>
Requires-Python: >=3.9
Description-Content-Type: text/markdown
License-Expression: BSD-3-Clause
Classifier: Development Status :: 5 - Production/Stable
Classifier: Environment :: Web Environment
Classifier: Framework :: Flask
Classifier: Intended Audience :: Developers
Classifier: Operating System :: OS Independent
Classifier: Programming Language :: Python
Classifier: Topic :: Internet :: WWW/HTTP :: Dynamic Content
Classifier: Topic :: Internet :: WWW/HTTP :: WSGI
Classifier: Topic :: Internet :: WWW/HTTP :: WSGI :: Application
Classifier: Topic :: Software Development :: Libraries :: Application Frameworks
Classifier: Typing :: Typed
License-File: LICENSE.txt
Requires-Dist: blinker>=1.9.0
Requires-Dist: click>=8.1.3
Requires-Dist: importlib-metadata>=3.6.0; python_version < '3.10'
Requires-Dist: itsdangerous>=2.2.0
Requires-Dist: jinja2>=3.1.2
Requires-Dist: markupsafe>=2.1.1
Requires-Dist: werkzeug>=3.1.0
Requires-Dist: asgiref>=3.2 ; extra == "async"
Requires-Dist: python-dotenv ; extra == "dotenv"
Project-URL: Changes, https://flask.palletsprojects.com/page/changes/
Project-URL: Chat, https://discord.gg/pallets
Project-URL: Documentation, https://flask.palletsprojects.com/
Project-URL: Donate, https://palletsprojects.com/donate
Project-URL: Source, https://github.com/pallets/flask/
Provides-Extra: async
Provides-Extra: dotenv

<div align="center"><img src="https://raw.githubusercontent.com/pallets/flask/refs/heads/stable/docs/_static/flask-name.svg" alt="" height="150"></div>

# Flask

Flask is a lightweight [WSGI] web application framework. It is designed
to make getting started quick and easy, with the ability to scale up to
complex applications. It began as a simple wrapper around [Werkzeug]
and [Jinja], and has become one of the most popular Python web
application frameworks.

Flask offers suggestions, but doesn't enforce any dependencies or
project layout. It is up to the developer to choose the tools and
libraries they want to use. There are many extensions provided by the
community that make adding new functionality easy.

[WSGI]: https://wsgi.readthedocs.io/
[Werkzeug]: https://werkzeug.palletsprojects.com/
[Jinja]: https://jinja.palletsprojects.com/

## A Simple Example

```python
# save this as app.py
from flask import Flask

app = Flask(__name__)

@app.route("/")
def hello():
    return "Hello, World!"
```

```
$ flask run
  * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
```

## Donate

The Pallets organization develops and supports Flask and the libraries
it uses. In order to grow the community of contributors and users, and
allow the maintainers to devote more time to the projects, [please
donate today].

[please donate today]: https://palletsprojects.com/donate

## Contributing

See our [detailed contributing documentation][contrib] for many ways to
contribute, including reporting issues, requesting features, asking or answering
questions, and making PRs.

[contrib]: https://palletsprojects.com/contributing/

