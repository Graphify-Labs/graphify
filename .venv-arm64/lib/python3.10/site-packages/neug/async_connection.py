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
"""The Neug async connection module."""

import asyncio
import random
from concurrent.futures import ThreadPoolExecutor

try:
    from neug_py_bind import PyConnection
except ImportError as e:
    import os

    if os.environ.get("BUILD_DOC", "OFF") == "OFF":
        # re-raise the import error if building documentation
        raise e

from neug.query_result import QueryResult


class AsyncConnection(object):
    """
    AsyncConnection represents a logical connection to a database that supports asynchronous operations.
    User should use this class to interact with the database asynchronously, such as executing queries
    and managing transactions.
    The connection is created by the `Database.async_connect` method, and should be closed by calling the `close` method
    when it is no longer needed. If the database is closed, all the connections to the database will be closed automatically.

    THe underlying implementation is based on the `Connection` class, which is implemented in C++ in a synchronous manner,
    But with a thread pool to execute the queries asynchronously.
    """

    def __init__(self, connection):  # connection: PyConnection
        """
        Initialize an AsyncConnection object.
        Parameters
        ----------
        py_connection : PyConnection
            The underlying c++ connection object that provides the actual database connection.
        """
        self._py_connection = connection
        self._loop = asyncio.get_event_loop()
        self._executor = ThreadPoolExecutor(
            max_workers=1,  # Use a single worker to ensure queries are executed sequentially
            thread_name_prefix="neug-async-connection-",
        )

    def __del__(self):
        self.close()

    def close(self):
        """Close the async connection."""
        if self._py_connection:
            self._py_connection.close()
            self._py_connection = None
        if self._executor:
            # cancel_future is only available in Python 3.9+, it will cancel all the pending futures in the executor,
            if hasattr(self._executor, "shutdown"):
                if hasattr(self._executor, "cancel_futures"):
                    self._executor.shutdown(wait=False, cancel_futures=True)
                else:
                    self._executor.shutdown(wait=False)
            self._executor = None

    async def execute(self, query: str) -> QueryResult:
        """
        Execute a cypher query on the database asynchronously. User could specify multiple queries in a single string,
        separated by semicolons. The query will be executed in the order they are specified.
        If any query fails, the whole execution will be rolled back.
        If you want to submit a query that may change the database schema, such as `CREATE TABLE`, `DROP TABLE`, etc.,
        or a query that may change the data in the database, such as `INSERT`, `UPDATE`, `DELETE`, etc.,
        you should avoid submitting multiple queries simultaneously. Instead, you should submit them one by one
        and wait for the result of each query before submitting the next one.

        For the details of the query syntax, please refer to the documentation of the cypher manual.
        The result of the query will be returned as a `QueryResult` object, which can be iterated to get the records.

        If the database is opened in read-only mode, the query will be executed in read-only mode,
        and any query that may change the database schema or data will fail with an error.
        If the database is opened in read-write mode, the query will be executed in read-write mode,
        and any query that may change the database schema or data will be executed successfully.

        .. code:: python
            >>> from neug import Database
            >>> db = Database("/tmp/test.db", mode="w")
            >>> conn = db.async_connect()
            >>> res = await conn.execute('CREATE TABLE person(id INT64, name STRING);')
            >>> for record in res:
            ...     print(record)

        Parameters
        ----------
        query : str
            The cypher query to be executed. Multiple queries can be specified in a single string,
            separated by ';'. The queries will be executed in the order they are specified.

        Returns
        -------
        query_result : QueryResult
            The result of the query execution, which is an instance of `QueryResult`.
        """
        return QueryResult(
            await self._loop.run_in_executor(
                self._executor, self._py_connection.execute, query
            )
        )
