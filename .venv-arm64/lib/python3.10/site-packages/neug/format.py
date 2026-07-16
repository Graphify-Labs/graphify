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

from tabulate import tabulate

from neug.query_result import QueryResult


def parse_and_format_results(pyquery_result: QueryResult, max_rows=20):
    """
    Parse and format the QueryResult structure for printing.

    Parameters
    ----------
    pyquery_result : QueryResult
        The result of the query.
    max_rows : int
        Maximum number of rows to print (default: 20).
    """
    headers = pyquery_result.column_names()
    rows = []

    total_records = len(pyquery_result)
    display_count = min(max_rows, total_records)
    for record in pyquery_result:
        current_row = []
        for column in record:
            current_row.append(parse_entry(column))
        rows.append(current_row)
        display_count -= 1
        if display_count <= 0:
            break
    if total_records > max_rows and rows:
        rows.append(["..."] * len(rows[0]))

    print_results_as_table(headers, rows)


def parse_entry(entry):
    """
    Parse individual entries in the QueryResult.

    Parameters
    ----------
    entry : object
        The entry to parse.

    Returns
    -------
    str
        The formatted entry.
    """
    if isinstance(entry, dict):
        # can be vertex, edge, property, map
        return (
            "{"
            + ", ".join(
                [f"{key}: {parse_entry(value)}" for key, value in entry.items()]
            )
            + "}"
        )
    elif isinstance(entry, list):
        # can be path, list
        return ", ".join([parse_entry(item) for item in entry])
    # simple types, can be bool, int, str, bytes, none, PyDate, PyDateTime, float, etc.
    else:
        return str(entry)


def print_results_as_table(headers, rows):
    """
    Print the results as a formatted table.

    Parameters
    ----------
    headers : list
        The headers for the table.
    rows : list
        The rows of the table.

    Returns
    -------
    None
    """
    print(tabulate(rows, headers=headers, tablefmt="grid"))
