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

import requests
import requests.adapters

try:
    from neug_py_bind import PyQueryRequest
    from neug_py_bind import PyQueryResult
except ImportError as e:
    import os

    if os.environ.get("BUILD_DOC", "OFF") == "OFF":
        # re-raise the import error if building documentation
        raise e

from neug.proto.error_pb2 import ERR_NETWORK
from neug.proto.error_pb2 import ERR_SESSION_CLOSED
from neug.query_result import QueryResult
from neug.utils import is_access_mode_valid
from neug.utils import valid_access_modes

logger = logging.getLogger(__name__)


class Session:
    """
    Session is a class that connects to the NeuG server. User could use it just like a normal NeuG Connection,
    while it is actually a session that connects to the NeuG server.

    A NeuG Server could be started with `Database::serve()` method, and it will listen to the specified endpoint.

    .. code:: python

        >>> from neug import Database
        >>> db = Database("/tmp/test.db", mode="w")
        >>> db.serve(port = 10000, host = "localhost")

    And on another python shell, user could connect to the NeuG server with the following code:

    .. code:: python

        >>> from neug import Session
        >>> sess = Session('http://localhost:10000', timeout='10s')
        >>> sess.execute('MATCH(n) return count(n)')

    The query will be sent to the NeuG http server, and the result will be returned as a response.
    The session will automatically handle the connection and disconnection to the server.

    To stop the NeuG server, user could send terminal signal to the process.
    To close the session, user could call the `close()` method.
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:10000",
        timeout: str = "10s",
        num_threads: int = 1,
    ):
        """
        Initialize a session with the given endpoint and timeout.

        :param endpoint: The endpoint URL for the session.
        :param timeout: The timeout duration for the session.
        """
        self._endpoint = endpoint
        self._query_endpoint = endpoint + "/cypher"
        self._status_endpoint = endpoint + "/service_status"
        self._schema_endpoint = endpoint + "/schema"
        self._timeout = timeout
        if isinstance(self._timeout, int):
            self._timeout = f"{self._timeout}s"
        self._http_session = requests.Session()
        self._http_adapter = requests.adapters.HTTPAdapter(
            pool_connections=num_threads,
            pool_maxsize=num_threads,
            max_retries=5,
            pool_block=False,
        )
        self._http_session.mount("http://", self._http_adapter)
        # check whether the endpoint is reachable
        try:
            self._http_session.get(self._status_endpoint, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Failed to connect to the endpoint {self._status_endpoint}: {e}"
            )
            raise ConnectionError(
                f"Could not connect to the endpoint: {self._status_endpoint}, Error code: {ERR_NETWORK}"
            ) from e
        logger.info(
            f"Session initialized with endpoint: {endpoint} and timeout: {self.timeout}"
        )
        self._closed = False

    @staticmethod
    def open(
        endpoint: str = "http://localhost:10000",
        timeout: str = "10s",
        num_threads: int = 1,
    ):
        """
        Open a session with the given endpoint and timeout.
        :param endpoint: The endpoint URL for the session.
        :param timeout: The timeout duration for the session.
        :return: An instance of the Session class.
        """
        logger.info(
            f"Opening session at endpoint: {endpoint} with timeout: {timeout}, num_threads: {num_threads}"
        )
        return Session(endpoint, timeout, num_threads)

    def close(self):
        """
        Close the session. This method is a placeholder for any cleanup operations.
        Currently, it does not perform any specific actions.
        """
        if self._closed:
            logger.warning("Session is already closed.")
            return
        logger.info(f"Closing session at endpoint: {self._endpoint}")
        self._closed = True
        self._http_session.close()
        self._http_adapter.close()
        self._http_session = None
        self._http_adapter = None

    def execute(
        self, query: str, access_mode: str = "", parameters: dict = None
    ) -> QueryResult:
        """
        Execute a query on the NeuG server.

        :param query: The query string to be executed.
        :param access_mode: The access mode for the query. Supported modes are:
            - `read` or `r`: Read-only queries
            - `insert` or `i`: Insert-only operations
            - `update` or `u`: Update/delete operations (default)
            - `schema` or `s`: Schema modification operations
        :param parameters: Optional dict of query parameters.
        :return: The result of the query execution.
        """
        if self._closed:
            logger.error("Session is closed. Cannot execute query.")
            raise ConnectionError(
                f"Session is closed. Cannot execute query, Error code: {ERR_SESSION_CLOSED}"
            )
        logger.info(
            f"Executing query: {query} on endpoint: {self._query_endpoint} with timeout: {self.timeout}"
        )
        access_mode = access_mode.lower()
        if access_mode != "" and not is_access_mode_valid(access_mode):
            raise ValueError(
                f"Invalid access_mode: {access_mode}. Supported access modes are "
                f"{valid_access_modes}."
            )
        try:
            if parameters is not None:
                payload = PyQueryRequest.serialize_request(
                    query, access_mode, parameters
                )
            else:
                payload = PyQueryRequest.serialize_request(query, access_mode)
            logger.info(f"Payload for query: {query} is {payload}")
            response = self._http_session.post(
                self._query_endpoint, data=payload, timeout=self.timeout
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to execute query: {query}. Error: {e}")
            raise ConnectionError(
                f"Could not execute query: {query}, Error code: {ERR_NETWORK}"
            ) from e
        if response.status_code != 200:
            error_message = f"Failed to execute query: {query}. Http code: {response.status_code}, Response: {response.text}"
            logger.error(error_message)
            raise Exception(error_message)

        return QueryResult(PyQueryResult(response._content))

    def service_status(self):
        """
        Get the service status of the NeuG server.

        :return: The status of the NeuG server.
        """
        logger.info(f"Fetching service status from endpoint: {self._status_endpoint}")
        try:
            response = self._http_session.get(
                self._status_endpoint, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch service status: {e}")
            raise ConnectionError("Could not fetch service status") from e

        # Json string
        return response.json()

    def get_schema(self):
        """
        Get the schema of the NeuG database.

        :return: The schema of the NeuG database.
        """
        logger.info(f"Fetching schema from endpoint: {self._schema_endpoint}")
        try:
            response = self._http_session.get(
                self._schema_endpoint, timeout=self.timeout
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch schema: {e}")
            raise ConnectionError("Could not fetch schema") from e
        # Json string
        return response.json()

    @property
    def timeout(self):
        """
        Get the timeout duration for the session, in seconds.
        """
        if isinstance(self._timeout, str):
            if self._timeout.endswith("s"):
                return int(self._timeout[:-1])
            elif self._timeout.endswith("ms"):
                return int(self._timeout[:-2]) / 1000
            else:
                raise ValueError("Timeout must be a string ending with 's' or 'ms'.")
        elif isinstance(self._timeout, int):
            return self._timeout
        else:
            raise TypeError("Timeout must be a string or an integer.")
