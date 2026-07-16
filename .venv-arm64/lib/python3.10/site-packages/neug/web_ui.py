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

import json
import logging
import os
import re
from pathlib import Path

from flask import Flask
from flask import jsonify
from flask import request
from flask import send_from_directory
from flask_cors import CORS

from neug.connection import Connection
from neug.database import Database
from neug.format import parse_and_format_results
from neug.session import Session

logger = logging.getLogger("neug")


class NeugWebUI:
    def __init__(self, db=None, connection=None, host="127.0.0.1", port=5000):
        self.app = Flask(__name__)
        CORS(self.app)  # Enable CORS for all routes

        self.db = db
        self.host = host
        self.port = port
        self.database = None
        self.session = connection

        # Setup routes
        self._setup_routes()

        # Initialize database connection if db is provided
        if self.db is not None:
            self._init_database()

    def _setup_routes(self):
        """Setup Flask routes"""

        @self.app.route("/")
        def index():
            """Serve the main index.html page"""
            resources_path = Path(__file__).parent / "resources"
            return send_from_directory(resources_path, "index.html")

        @self.app.route("/schema", methods=["GET"])
        def get_schema():
            return self.session.get_schema()

        @self.app.route(
            "/cypherv2", methods=["POST"]
        )  # TODO(zhanglei): change cypherv2 to cypher
        def execute_query():
            # Get raw string from request body
            query = request.get_data(as_text=True)
            logger.info(f"Received query: {query}")
            try:
                return self.session.execute(query).get_bolt_response()
            except Exception as e:
                logger.error(f"Error executing query: {e}")
                return str(e), 500

    def _init_database(self):
        """Initialize database connection"""
        pattern_http = re.compile(r"^http://([a-zA-Z0-9.-_]+):(\d+)$")
        pattern_plain = re.compile(r"^([a-zA-Z0-9.-_]+):(\d+)$")

        if self.db is None:
            match_http = match_plain = False
        else:
            match_http = pattern_http.fullmatch(self.db)
            match_plain = pattern_plain.fullmatch(self.db)

        if match_http:
            endpoint = f"http://{match_http.group(1)}:{match_http.group(2)}/"
        elif match_plain:
            endpoint = f"http://{match_plain.group(1)}:{match_plain.group(2)}/"
        else:
            self.database = Database(db_path=self.db, mode="w")
            endpoint = self.database.serve(
                port=self.port + 1, host=self.host, blocking=False
            )
            logger.info(f"Database server started at {endpoint}")
        self.session = Session(endpoint=endpoint)

    def run(self, debug=False):
        """Start the Flask development server"""
        logger.info(f"Starting Neug Web UI on http://{self.host}:{self.port}")
        if self.db:
            logger.info(f"Connected to database: {self.db}")

        self.app.run(host=self.host, port=self.port, debug=debug)


def start_web_ui(db=None, host="127.0.0.1", port=5000, debug=False):
    """Start the Neug Web UI"""
    web_ui = NeugWebUI(db=db, host=host, port=port)
    web_ui.run(debug=debug)


if __name__ == "__main__":
    start_web_ui()
