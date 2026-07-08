"""CLI entry point for graphify-live - enhanced animated HTML visualization.

Usage:
    graphify-live export html /path/to/project

All subcommands work identically to `graphify` except that `export html`
uses the enhanced animated D3.js HTML exporter instead of the default
vis-network exporter.
"""


def main():
    import graphify.export
    import graphify.export_live

    graphify.export.to_html = graphify.export_live.to_html

    from graphify.__main__ import main as _original_main

    _original_main()


if __name__ == "__main__":
    main()
