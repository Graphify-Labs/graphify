# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Contains the Duration helper APIs."""

import datetime

from google.protobuf.duration_pb2 import Duration


def from_json_string(value: str) -> Duration:
  """Converts a string to Duration.

  Args:
    value: A string to be converted. The string must end with 's'. Any
      fractional digits (or none) are accepted as long as they fit into
      precision. For example: "1s", "1.01s", "1.0000001s", "-3.100s"

  Raises:
    ValueError: On parsing problems.
  """
  duration = Duration()
  duration.FromJsonString(value)
  return duration


def from_microseconds(micros: float) -> Duration:
  """Converts microseconds to Duration."""
  duration = Duration()
  duration.FromMicroseconds(micros)
  return duration


def from_milliseconds(millis: float) -> Duration:
  """Converts milliseconds to Duration."""
  duration = Duration()
  duration.FromMilliseconds(millis)
  return duration


def from_nanoseconds(nanos: float) -> Duration:
  """Converts nanoseconds to Duration."""
  duration = Duration()
  duration.FromNanoseconds(nanos)
  return duration


def from_seconds(seconds: float) -> Duration:
  """Converts seconds to Duration."""
  duration = Duration()
  duration.FromSeconds(seconds)
  return duration


def from_timedelta(td: datetime.timedelta) -> Duration:
  """Converts timedelta to Duration."""
  duration = Duration()
  duration.FromTimedelta(td)
  return duration


def to_json_string(duration: Duration) -> str:
  """Converts Duration to string format.

  Returns:
    A string converted from self. The string format will contains
    3, 6, or 9 fractional digits depending on the precision required to
    represent the exact Duration value. For example: "1s", "1.010s",
    "1.000000100s", "-3.100s"
  """
  return duration.ToJsonString()


def to_microseconds(duration: Duration) -> int:
  """Converts a Duration to microseconds."""
  return duration.ToMicroseconds()


def to_milliseconds(duration: Duration) -> int:
  """Converts a Duration to milliseconds."""
  return duration.ToMilliseconds()


def to_nanoseconds(duration: Duration) -> int:
  """Converts a Duration to nanoseconds."""
  return duration.ToNanoseconds()


def to_seconds(duration: Duration) -> int:
  """Converts a Duration to seconds."""
  return duration.ToSeconds()


def to_timedelta(duration: Duration) -> datetime.timedelta:
  """Converts Duration to timedelta."""
  return duration.ToTimedelta()
