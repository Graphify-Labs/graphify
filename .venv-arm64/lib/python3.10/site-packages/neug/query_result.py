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

"""The Neug result module."""

try:
    from neug_py_bind import PyQueryResult
except ImportError as e:
    import os

    if os.environ.get("BUILD_DOC", "OFF") == "OFF":
        # re-raise the import error if building documentation
        raise e

# PyQueryResult is defined in the neug_py_bind module, which is a C++ binding for the Python interface.
# See py_query_result.h for the definition of PyQueryResult.


class QueryResult(object):
    """
    QueryResult represents the result of a cypher query. Could be visited as a iterator.

    It has the following methods to iterate over the results.
        - `hasNext()`: Returns True if there are more results to iterate over.
        - `getNext()`: Returns the next result as a list.
        - `length()`: Returns the total number of results.
        - `column_names()`: Returns the projected column names as strings.

    .. code:: python

        >>> from neug import Database
        >>> db = Database("/tmp/test.db", mode="r")
        >>> conn = db.connect()
        >>> result = conn.execute('MATCH (n) RETURN n')
        >>> for row in result:
        >>>     print(row)
    """

    def __init__(self, result):  # result: PyQueryResult
        """
        Initialize the QueryResult.

        Parameters
        ----------
        result : PyQueryResult
            The result of the query, returned by the query engine. It is a C++ object and is exported to python via pybind.
        """
        self._result = result

    def __iter__(self):
        """
        Iterate over the result.
        """
        return self

    def __next__(self):
        if self._result.hasNext():
            return self._result.getNext()  # Returns a list
        else:
            raise StopIteration

    def __len__(self):
        """
        Get the length of the result.
        """
        return self._result.length()

    def __str__(self):
        """
        Get the string representation of the result.

        Returns
        -------
        str
            The string representation of the result.
        """
        return f"QueryResult(size {self._result.length()})"

    def __getitem__(self, index):
        """
        Get the result at the specified index.

        Parameters
        ----------
        index : int
            The index of the result to retrieve.

        Returns
        -------
        list
            The result at the specified index, which is a list of values.

        Raises
        ------
        IndexError
            If the index is out of range.
        """
        return self._result[index]

    def __repr__(self):
        """
        Get the string representation of the result.

        Returns
        -------
        str
            The string representation of the result.
        """
        return self.__str__()

    def __del__(self):
        """
        Delete the QueryResult.
        """
        del self._result
        self._result = None

    def column_names(self):
        """Return the projected column names as a list of strings."""
        return self._result.column_names()

    def get_bolt_response(self) -> str:
        """
        Get the result in Bolt response format.
        TODO(zhanglei,xiaoli): Make sure the format consistency with neo4j bolt response.

        Returns
        -------
        str
            The result in Bolt response format.
        """
        return self._result.get_bolt_response()

    def to_arrow(self):
        """
        Convert the result to an Arrow table.

        Returns
        -------
        pyarrow.Table
            The result converted to an Arrow table.
        """
        return self._result.to_arrow()
