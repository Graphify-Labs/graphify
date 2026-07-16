"""When it comes to combining multiple controller or view functions
(however you want to call them) you need a dispatcher. A simple way
would be applying regular expression tests on the ``PATH_INFO`` and
calling registered callback functions that return the value then.

This module implements a much more powerful system than simple regular
expression matching because it can also convert values in the URLs and
build URLs.

Here a simple example that creates a URL map for an application with
two subdomains (www and kb) and some URL rules:

.. code-block:: python

    m = Map([
        # Static URLs
        Rule('/', endpoint='static/index'),
        Rule('/about', endpoint='static/about'),
        Rule('/help', endpoint='static/help'),
        # Knowledge Base
        Subdomain('kb', [
            Rule('/', endpoint='kb/index'),
            Rule('/browse/', endpoint='kb/browse'),
            Rule('/browse/<int:id>/', endpoint='kb/browse'),
            Rule('/browse/<int:id>/<int:page>', endpoint='kb/browse')
        ])
    ], default_subdomain='www')

If the application doesn't use subdomains it's perfectly fine to not set
the default subdomain and not use the `Subdomain` rule factory. The
endpoint in the rules can be anything, for example import paths or
unique identifiers. The WSGI application can use those endpoints to get the
handler for that URL.  It doesn't have to be a string at all but it's
recommended.

Now it's possible to create a URL adapter for one of the subdomains and
build URLs:

.. code-block:: python

    c = m.bind('example.com')

    c.build("kb/browse", dict(id=42))
    'http://kb.example.com/browse/42/'

    c.build("kb/browse", dict())
    'http://kb.example.com/browse/'

    c.build("kb/browse", dict(id=42, page=3))
    'http://kb.example.com/browse/42/3'

    c.build("static/about")
    '/about'

    c.build("static/index", force_external=True)
    'http://www.example.com/'

    c = m.bind('example.com', subdomain='kb')

    c.build("static/about")
    'http://www.example.com/about'

The first argument to bind is the server name *without* the subdomain.
Per default it will assume that the script is mounted on the root, but
often that's not the case so you can provide the real mount point as
second argument:

.. code-block:: python

    c = m.bind('example.com', '/applications/example')

The third argument can be the subdomain, if not given the default
subdomain is used.  For more details about binding have a look at the
documentation of the `MapAdapter`.

And here is how you can match URLs:

.. code-block:: python

    c = m.bind('example.com')

    c.match("/")
    ('static/index', {})

    c.match("/about")
    ('static/about', {})

    c = m.bind('example.com', '/', 'kb')

    c.match("/")
    ('kb/index', {})

    c.match("/browse/42/23")
    ('kb/browse', {'id': 42, 'page': 23})

If matching fails you get a ``NotFound`` exception, if the rule thinks
it's a good idea to redirect (for example because the URL was defined
to have a slash at the end but the request was missing that slash) it
will raise a ``RequestRedirect`` exception. Both are subclasses of
``HTTPException`` so you can use those errors as responses in the
application.

If matching succeeded but the URL rule was incompatible to the given
method (for example there were only rules for ``GET`` and ``HEAD`` but
routing tried to match a ``POST`` request) a ``MethodNotAllowed``
exception is raised.
"""

from .converters import AnyConverter as AnyConverter
from .converters import BaseConverter as BaseConverter
from .converters import FloatConverter as FloatConverter
from .converters import IntegerConverter as IntegerConverter
from .converters import PathConverter as PathConverter
from .converters import UnicodeConverter as UnicodeConverter
from .converters import UUIDConverter as UUIDConverter
from .converters import ValidationError as ValidationError
from .exceptions import BuildError as BuildError
from .exceptions import NoMatch as NoMatch
from .exceptions import RequestAliasRedirect as RequestAliasRedirect
from .exceptions import RequestPath as RequestPath
from .exceptions import RequestRedirect as RequestRedirect
from .exceptions import RoutingException as RoutingException
from .exceptions import WebsocketMismatch as WebsocketMismatch
from .map import Map as Map
from .map import MapAdapter as MapAdapter
from .matcher import StateMachineMatcher as StateMachineMatcher
from .rules import EndpointPrefix as EndpointPrefix
from .rules import parse_converter_args as parse_converter_args
from .rules import Rule as Rule
from .rules import RuleFactory as RuleFactory
from .rules import RuleTemplate as RuleTemplate
from .rules import RuleTemplateFactory as RuleTemplateFactory
from .rules import Subdomain as Subdomain
from .rules import Submount as Submount
