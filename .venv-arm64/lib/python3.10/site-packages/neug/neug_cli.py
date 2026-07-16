#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2020 Alibaba Group Holding Limited. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import atexit
import cmd
import errno
import logging
import os
import re
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("neug")

try:
    import readline  # type: ignore
except ImportError:
    readline = None
    logger.warning(
        "readline module is unavailable; command history features are disabled"
    )

import click

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggest
    from prompt_toolkit.auto_suggest import Suggestion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.lexers import Lexer
    from prompt_toolkit.styles import Style
except ImportError:
    PromptSession = None
    AutoSuggest = object
    Suggestion = None
    FileHistory = None
    KeyBindings = None
    Lexer = object
    Style = None

from neug.connection import Connection
from neug.database import Database
from neug.format import parse_and_format_results

# Build-in commands
COMMAND_HELP = ":help"
COMMAND_QUIT = ":quit"
COMMAND_MAX_ROWS = ":max_rows"
COMMAND_UI = ":ui"
SHELL_COMMANDS = [COMMAND_HELP, COMMAND_QUIT, COMMAND_MAX_ROWS, COMMAND_UI]
CYPHER_KEYWORDS = [
    "MATCH",
    "OPTIONAL MATCH",
    "WHERE",
    "RETURN",
    "WITH",
    "CREATE",
    "MERGE",
    "SET",
    "DELETE",
    "DETACH DELETE",
    "UNWIND",
    "ORDER BY",
    "LIMIT",
    "SKIP",
    "AS",
    "AND",
    "OR",
    "NOT",
    "IN",
    "IS NULL",
    "IS NOT NULL",
    "ACYCLIC",
    "ANY",
    "ADD",
    "ALL",
    "ALTER",
    "ASC",
    "ASCENDING",
    "ATTACH",
    "BEGIN",
    "BY",
    "CALL",
    "CASE",
    "CAST",
    "CHECKPOINT",
    "COLUMN",
    "COMMENT",
    "COMMIT",
    "COMMIT_SKIP_CHECKPOINT",
    "CONTAINS",
    "COPY",
    "COUNT",
    "CYCLE",
    "DATABASE",
    "DBTYPE",
    "DEFAULT",
    "DESC",
    "DESCENDING",
    "DETACH",
    "DISTINCT",
    "DROP",
    "ELSE",
    "END",
    "ENDS",
    "EXISTS",
    "EXPLAIN",
    "EXPORT",
    "EXTENSION",
    "FROM",
    "GLOB",
    "GRAPH",
    "GROUP",
    "HEADERS",
    "HINT",
    "IMPORT",
    "IF",
    "INCREMENT",
    "INSTALL",
    "IS",
    "JOIN",
    "KEY",
    "LOAD",
    "LOGICAL",
    "MACRO",
    "MAXVALUE",
    "MINVALUE",
    "MULTI_JOIN",
    "NO",
    "NODE",
    "NONE",
    "NULL",
    "ON",
    "ONLY",
    "OPTIONAL",
    "ORDER",
    "PRIMARY",
    "PROFILE",
    "PROJECT",
    "READ",
    "REL",
    "RENAME",
    "ROLLBACK",
    "ROLLBACK_SKIP_CHECKPOINT",
    "SEQUENCE",
    "SHORTEST",
    "START",
    "STARTS",
    "TABLE",
    "THEN",
    "TO",
    "TRAIL",
    "TRANSACTION",
    "TYPE",
    "UNINSTALL",
    "UNION",
    "USE",
    "WHEN",
    "WRITE",
    "WSHORTEST",
    "XOR",
    "SINGLE",
    "YIELD",
]
BUILTIN_FUNCTIONS = [
    "COUNT",
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "COLLECT",
    "ID",
    "LABEL",
    "LABELS",
    "NODES",
    "RELS",
    "RELATIONSHIPS",
    "PROPERTIES",
    "LENGTH",
    "START_NODE",
    "END_NODE",
    "LOWER",
    "UPPER",
    "REVERSE",
    "CONTAINS",
    "STARTS_WITH",
    "ENDS_WITH",
    "TOLOWER",
    "TOUPPER",
    "LCASE",
    "UCASE",
    "CAST",
    "DATE",
    "TIMESTAMP",
    "DURATION",
    "DATE_PART",
    "DATEPART",
]

# Default prompt
PROMPT = "neug > "
ALTPROMPT = "... "
PROMPT_TOKENS = [("class:prompt", "neug"), ("class:prompt-symbol", " > ")]
ALTPROMPT_TOKENS = [("class:prompt-symbol", "... ")]
SHELL_STYLE = (
    Style.from_dict(
        {
            "prompt": "ansicyan bold",
            "prompt-symbol": "ansibrightblack",
            "auto-suggestion": "#777777",
            "command": "ansigreen bold",
            "cypher-keyword": "ansigreen bold",
            "error": "ansired",
        }
    )
    if Style
    else None
)
CYPHER_CANDIDATES = CYPHER_KEYWORDS + BUILTIN_FUNCTIONS
CYPHER_KEYWORDS_BY_LENGTH = sorted(CYPHER_KEYWORDS, key=len, reverse=True)
CYPHER_KEYWORD_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(keyword) for keyword in CYPHER_KEYWORDS_BY_LENGTH)
    + r")\b",
    re.IGNORECASE,
)


def _format_like_typed(candidate, typed):
    if typed.islower():
        return candidate.lower()
    if typed.isupper():
        return candidate.upper()
    if typed[:1].isupper() and typed[1:].islower():
        return candidate.capitalize()
    return candidate.lower()


def _deduplicate(items):
    seen = set()
    result = []
    for item in items:
        normalized = item.upper()
        if normalized not in seen:
            seen.add(normalized)
            result.append(item)
    return result


def _matching_candidates(fragment, candidates):
    upper_fragment = fragment.upper()
    return [
        candidate for candidate in candidates if candidate.startswith(upper_fragment)
    ]


def _candidate_suffix(candidate, fragment):
    formatted = _format_like_typed(candidate, fragment)
    return formatted[len(fragment) :]


def _current_cypher_fragment(text):
    fragments = re.findall(r"\S+", text)
    for size in range(min(3, len(fragments)), 0, -1):
        fragment = " ".join(fragments[-size:])
        if text.endswith(fragment):
            matches = _matching_candidates(fragment, CYPHER_CANDIDATES)
            if matches:
                return fragment
    return None


def _completion_candidates(text):
    stripped = text.lstrip()
    if stripped.startswith(":"):
        commands = [
            command for command in SHELL_COMMANDS if command.startswith(stripped)
        ]
        return stripped, commands

    fragment = _current_cypher_fragment(stripped)
    if not fragment:
        return "", []
    return fragment, _deduplicate(_matching_candidates(fragment, CYPHER_CANDIDATES))


def _suggestion_for_index(text, index=0):
    fragment, candidates = _completion_candidates(text)
    if not fragment or not candidates:
        return None
    candidate = candidates[index % len(candidates)]
    return _candidate_suffix(candidate, fragment)


def _lex_cypher_line(line):
    tokens = []
    position = 0
    for match in CYPHER_KEYWORD_PATTERN.finditer(line):
        if match.start() > position:
            tokens.append(("", line[position : match.start()]))
        tokens.append(("class:cypher-keyword", line[match.start() : match.end()]))
        position = match.end()
    if position < len(line):
        remaining = line[position:]
        partial_match = re.match(r"\S+$", remaining)
        if partial_match:
            before_partial = remaining[: partial_match.start()]
            partial = partial_match.group(0)
            if before_partial:
                tokens.append(("", before_partial))
            if _matching_candidates(partial, CYPHER_KEYWORDS):
                tokens.append(("class:cypher-keyword", partial))
            else:
                tokens.append(("", partial))
        else:
            tokens.append(("", remaining))
    return tokens


class NeugAutoSuggest(AutoSuggest):
    def get_suggestion(self, buffer, document):
        text = document.text_before_cursor
        if buffer:
            state = getattr(buffer, "_neug_completion_state", None)
            if state and state.get("text") == text:
                suggestion = _suggestion_for_index(text, state.get("index", 0))
                if suggestion:
                    return Suggestion(suggestion)

        suggestion = _suggestion_for_index(text)
        if suggestion:
            return Suggestion(suggestion)
        return None


def _refresh_buffer_suggestion(buffer):
    if buffer.auto_suggest:
        buffer.suggestion = buffer.auto_suggest.get_suggestion(buffer, buffer.document)
    else:
        buffer.suggestion = None
    buffer.on_suggestion_set.fire()


def _handle_tab(buffer):
    text = buffer.document.text_before_cursor
    fragment, candidates = _completion_candidates(text)
    if not fragment or not candidates:
        return False

    state = getattr(buffer, "_neug_completion_state", None)
    same_cycle = (
        state
        and state.get("text") == text
        and state.get("fragment") == fragment
        and state.get("candidates") == candidates
    )
    if len(candidates) == 1:
        suggestion = _suggestion_for_index(text)
        if suggestion:
            buffer.insert_text(suggestion)
            buffer._neug_completion_state = None
            return True
        return False

    index = (state.get("index", 0) + 1) % len(candidates) if same_cycle else 1
    buffer._neug_completion_state = {
        "text": text,
        "fragment": fragment,
        "candidates": candidates,
        "index": index,
    }
    _refresh_buffer_suggestion(buffer)
    return True


def create_key_bindings():
    bindings = KeyBindings()

    @bindings.add("tab")
    def _(event):
        _handle_tab(event.current_buffer)

    return bindings


class NeugLexer(Lexer):
    def lex_document(self, document):
        def get_line(lineno):
            line = document.lines[lineno]
            stripped = line.lstrip()
            leading_spaces = len(line) - len(stripped)
            tokens = []
            if leading_spaces:
                tokens.append(("", line[:leading_spaces]))
            if stripped.startswith(":"):
                command = next(
                    (cmd for cmd in SHELL_COMMANDS if cmd.startswith(stripped)), None
                )
                if command:
                    typed_len = min(len(stripped), len(command))
                    tokens.append(("class:command", stripped[:typed_len]))
                    tokens.append(("class:auto-suggestion", stripped[typed_len:]))
                    return tokens
                tokens.append(("class:error", stripped))
                return tokens
            tokens.extend(_lex_cypher_line(stripped))
            return tokens

        return get_line


class NeugShell(cmd.Cmd):
    intro = "Welcome to the Neug shell. Type :help for usage hints.\n"
    prompt = PROMPT

    def __init__(self, connection):
        super().__init__()
        self.connection = connection
        self.buffer = []
        self.multi_line_mode = False
        self.max_rows = 20  # Default max rows for query results
        self._histfile = os.path.join(os.path.expanduser("~"), ".neug_history")
        self._prompt_session = None

        if not PromptSession:
            if readline:
                try:
                    readline.read_history_file(self._histfile)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    # OSError (errno 22/EINVAL): libedit (macOS) cannot parse a
                    # GNU readline history file. Safe to ignore.
                    # Re-raise for any other OS error (e.g. EPERM) so unexpected
                    # problems still surface to the user.
                    if e.errno != errno.EINVAL:
                        raise
                atexit.register(self._save_history, self._histfile)
            else:
                logger.info("Command history disabled; readline support not detected.")

        logger.info("Connection established.")

    def _save_history(self, histfile):
        """Save command history with error handling"""
        if not readline:
            return
        try:
            readline.write_history_file(histfile)
        except (PermissionError, OSError) as e:
            logger.warning(f"Could not save history to {histfile}: {e}")

    def cmdloop(self, intro=None):
        if not PromptSession:
            return super().cmdloop(intro=intro)

        self._prompt_session = PromptSession(
            history=FileHistory(self._histfile),
            auto_suggest=NeugAutoSuggest(),
            key_bindings=create_key_bindings(),
            lexer=NeugLexer(),
            style=SHELL_STYLE,
        )

        if intro is None:
            intro = self.intro
        if intro:
            print(intro, end="")

        while True:
            try:
                line = self._prompt_session.prompt(
                    ALTPROMPT_TOKENS if self.multi_line_mode else PROMPT_TOKENS
                )
            except (EOFError, KeyboardInterrupt):
                print("Exiting...")
                self.connection.close()
                return True
            if not line.strip():
                continue
            if self.default(line):
                return True

    def emptyline(self):
        """Override default emptyline behavior to do nothing instead of repeating the last command."""
        pass

    def do_quit(self, arg):
        """Exit the shell: quit"""
        print("Exiting...")
        self.connection.close()
        return True

    def default(self, line):
        """Handles any input not matched by a command method."""
        stripped_line = line.strip()
        if stripped_line.startswith(COMMAND_HELP):
            # Handle help command
            self.do_help(stripped_line)
        elif stripped_line.startswith(COMMAND_QUIT):
            # Handle quit command
            return self.do_quit(stripped_line)
        elif stripped_line.startswith(COMMAND_MAX_ROWS):
            # Handle max_rows command
            arg = stripped_line[len(COMMAND_MAX_ROWS) :].strip()
            self.do_max_rows(arg)
        elif stripped_line.startswith(COMMAND_UI):
            arg = stripped_line[len(COMMAND_UI) :].strip()
            self.do_ui(arg)
        elif stripped_line:
            self.buffer.append(stripped_line)
            self.multi_line_mode = not stripped_line.endswith(";")
            # Support multi-line commands
            if not self.multi_line_mode:
                full_query = " ".join(self.buffer)
                self.buffer = []
                self.prompt = PROMPT
                self.do_query(full_query)
                # Add complete query to history after execution
                if readline and not self._prompt_session:
                    readline.add_history(full_query)
            else:
                self.prompt = ALTPROMPT
        else:
            print("Invalid command. Type :help for usage hints.")

    def do_query(self, arg):
        """Execute a Cypher query"""
        try:
            result = self.connection.execute(arg)
            if result:
                parse_and_format_results(result, max_rows=self.max_rows)
        except Exception as e:
            print(e)

    def do_max_rows(self, arg):
        """Set the maximum number of rows to display for query results. Usage: :max_rows 10"""
        try:
            value = int(arg.strip())
            if value <= 0:
                print("max_rows must be a positive integer.")
                return
            self.max_rows = value
            print(f"Set max_rows to {self.max_rows}")
        except Exception:
            print("Usage: :max_rows <number>")

    def do_ui(self, arg):
        host = "127.0.0.1"
        port = 5000
        try:
            value = arg.strip()
            if len(value) > 0:
                pattern_plain = re.compile(r"^([a-zA-Z0-9.-_]+):(\d+)$")
                match_plain = pattern_plain.fullmatch(value)
                if match_plain:
                    host = match_plain.group(1)
                    port = match_plain.group(2)
                else:
                    print(f"Invalid endpoint: {value}")
                    return
        except Exception:
            print("Usage: :ui <host:port>")
            return
        try:
            from neug.web_ui import NeugWebUI

            web_ui = NeugWebUI(connection=self.connection, host=host, port=port)
            web_ui.run()

        except ImportError as e:
            click.echo(f"Error: Flask dependencies not installed. {e}")
            click.echo("Please install with: pip install flask flask-cors")
        except Exception as e:
            click.echo(f"Error starting web UI: {e}")
        return

    def do_help(self, arg):
        """Provide usage hints."""
        print(
            """
            Usage hints:
            - Enter Cypher queries directly to execute them on the connected database.
            - Use :help to display this help message.
            - Use :quit to leave the shell.
            - Use :max_rows <number> to set the maximum number of rows to display for query results.
            - Use :ui <endpoint> to start a web ui service on endpoint.
            - Multi-line commands are supported. Use ';' at the end to execute.
            - Command history is supported; use the up/down arrow keys to navigate previous commands.
            - Use Tab to cycle candidates and right arrow to accept the current suggestion.
            """
        )


@click.group(
    name="neug-cli",
    epilog="Run 'neug-cli COMMAND --help' for more information on a command.\n\n  e.g. neug-cli open --help",
)
@click.version_option(version="0.1.3")
def cli():
    """Neug CLI Tool."""


@cli.command()
@click.argument("db_uri", default="", required=False)
@click.option(
    "-m",
    "--mode",
    default="read-write",
    help="Database mode: read-only or read-write (default: read-write).",
)
def open(db_uri, mode):
    """Open a local database.

    Start an interactive shell with a local NeuG database.
    If DB_URI is omitted, an in-memory database is used.

    Examples:

      neug-cli open /path/to/db

      neug-cli open /path/to/db -m read-only

      neug-cli open
    """
    if len(db_uri) > 0:
        click.echo(f"Opened database at {db_uri} in {mode} mode")
    else:
        click.echo("Opened in-memory database in read-write mode")
    database = Database(db_path=str(db_uri), mode=mode)
    connection = database.connect()
    shell = NeugShell(connection)
    shell.cmdloop()


@cli.command()
@click.argument("db_uri", required=True)
@click.option(
    "--timeout", default=300, show_default=True, help="Connection timeout in seconds."
)
def connect(db_uri, timeout):
    """Connect to a remote database.

    Start an interactive shell connected to a remote NeuG server.
    DB_URI should be in the format host:port or http://host:port.

    Examples:

      neug-cli connect localhost:8182

      neug-cli connect http://192.168.1.1:8182 --timeout 60
    """
    click.echo(f"{db_uri}")
    pattern_http = re.compile(r"^http://([a-zA-Z0-9.-_]+):(\d+)$")
    pattern_plain = re.compile(r"^([a-zA-Z0-9.-_]+):(\d+)$")

    if db_uri is None:
        match_http = match_plain = False
    else:
        match_http = pattern_http.fullmatch(db_uri)
        match_plain = pattern_plain.fullmatch(db_uri)

    if match_http:
        host = match_http.group(1)
        port = match_http.group(2)
    elif match_plain:
        host = match_plain.group(1)
        port = match_plain.group(2)
    else:
        click.echo(f"Invalid db_uri: {db_uri}")
    click.echo(f"Connecting to {host}:{port}")

    from neug.session import Session

    session = Session.open(f"http://{host}:{port}/", timeout=timeout)
    shell = NeugShell(session)
    shell.cmdloop()


if __name__ == "__main__":
    cli()
