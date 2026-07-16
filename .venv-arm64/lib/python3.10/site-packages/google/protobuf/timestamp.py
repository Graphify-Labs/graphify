# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Contains the Timestamp helper APIs."""

import datetime
from typing import Optional

from google.protobuf.timestamp_pb2 import Timestamp


def from_json_string(value: str) -> Timestamp:
  """Parse a RFC 3339 date string format to Timestamp.

  Args:
    value: A date string. Any fractional digits (or none) and any offset are
      accepted as long as they fit into nano-seconds precision. Example of
      accepted format: '1972-01-01T10:00:20.021-05:00'

  Raises:
    ValueError: On parsing problems.
  """
  timestamp = Timestamp()
  timestamp.FromJsonString(value)
  return timestamp


def from_microseconds(micros: float) -> Timestamp:
  """Converts microseconds since epoch to Timestamp."""
  timestamp = Timestamp()
  timestamp.FromMicroseconds(micros)
  return timestamp


def from_milliseconds(millis: float) -> Timestamp:
  """Converts milliseconds since epoch to Timestamp."""
  timestamp = Timestamp()
  timestamp.FromMilliseconds(millis)
  return timestamp


def from_nanoseconds(nanos: float) -> Timestamp:
  """Converts nanoseconds since epoch to Timestamp."""
  timestamp = Timestamp()
  timestamp.FromNanoseconds(nanos)
  return timestamp


def from_seconds(seconds: float) -> Timestamp:
  """Converts seconds since epoch to Timestamp."""
  timestamp = Timestamp()
  timestamp.FromSeconds(seconds)
  return timestamp


def from_current_time() -> Timestamp:
  """Converts the current UTC to Timestamp."""
  timestamp = Timestamp()
  timestamp.FromDatetime(datetime.datetime.now(tz=datetime.timezone.utc))
  return timestamp


def to_json_string(ts: Timestamp) -> str:
  """Converts Timestamp to RFC 3339 date string format.

  Returns:
    A string converted from timestamp. The string is always Z-normalized
    and uses 3, 6 or 9 fractional digits as required to represent the
    exact time. Example of the return format: '1972-01-01T10:00:20.021Z'
  """
  return ts.ToJsonString()


def to_microseconds(ts: Timestamp) -> int:
  """Converts Timestamp to microseconds since epoch."""
  return ts.ToMicroseconds()


def to_milliseconds(ts: Timestamp) -> int:
  """Converts Timestamp to milliseconds since epoch."""
  return ts.ToMilliseconds()


def to_nanoseconds(ts: Timestamp) -> int:
  """Converts Timestamp to nanoseconds since epoch."""
  return ts.ToNanoseconds()


def to_seconds(ts: Timestamp) -> int:
  """Converts Timestamp to seconds since epoch."""
  return ts.ToSeconds()


def to_datetime(
    ts: Timestamp, tz: Optional[datetime.tzinfo] = None
) -> datetime.datetime:
  """Converts Timestamp to a datetime.

  Args:
    tz: A datetime.tzinfo subclass; defaults to None.

  Returns:
    If tzinfo is None, returns a timezone-naive UTC datetime (with no timezone
    information, i.e. not aware that it's UTC).

    Otherwise, returns a timezone-aware datetime in the input timezone.
  """
  return ts.ToDatetime(tzinfo=tz)
