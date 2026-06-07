"""graphify.cli - subcommands split out of __main__.py.

Currently hosts the platform installers (see ``cli.installers``). Future
phases may move the ``extract`` / ``query`` / ``build`` / ``analyze``
/ ``export`` dispatchers here as well; until then, ``__main__.main``
remains the single CLI entry point and re-exports the installer
functions for backward compatibility.
"""
