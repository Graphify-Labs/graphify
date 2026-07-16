# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Contains the Nextgen Pythonic protobuf APIs."""

import io
from typing import Type, TypeVar

from google.protobuf.internal import decoder
from google.protobuf.internal import encoder
from google.protobuf.message import Message

_MESSAGE = TypeVar('_MESSAGE', bound='Message')


def serialize(message: _MESSAGE, deterministic: bool = None) -> bytes:
  """Return the serialized proto.

  Args:
    message: The proto message to be serialized.
    deterministic: If true, requests deterministic serialization
        of the protobuf, with predictable ordering of map keys.

  Returns:
    A binary bytes representation of the message.
  """
  return message.SerializeToString(deterministic=deterministic)


def parse(message_class: Type[_MESSAGE], payload: bytes) -> _MESSAGE:
  """Given a serialized data in binary form, deserialize it into a Message.

  Args:
    message_class: The message meta class.
    payload: A serialized bytes in binary form.

  Returns:
    A new message deserialized from payload.
  """
  new_message = message_class()
  new_message.ParseFromString(payload)
  return new_message


def serialize_length_prefixed(message: _MESSAGE, output: io.BytesIO) -> None:
  """Writes the size of the message as a varint and the serialized message.

  Writes the size of the message as a varint and then the serialized message.
  This allows more data to be written to the output after the message. Use
  parse_length_prefixed to parse messages written by this method.

  The output stream must be buffered, e.g. using
  https://docs.python.org/3/library/io.html#buffered-streams.

  Example usage:
    out = io.BytesIO()
    for msg in message_list:
      proto.serialize_length_prefixed(msg, out)

  Args:
    message: The protocol buffer message that should be serialized.
    output: BytesIO or custom buffered IO that data should be written to.
  """
  size = message.ByteSize()
  encoder._VarintEncoder()(output.write, size)
  out_size = output.write(serialize(message))

  if out_size != size:
    raise TypeError(
        'Failed to write complete message (wrote: %d, expected: %d)'
        '. Ensure output is using buffered IO.' % (out_size, size)
    )


def parse_length_prefixed(
    message_class: Type[_MESSAGE], input_bytes: io.BytesIO
) -> _MESSAGE:
  """Parse a message from input_bytes.

  Args:
    message_class: The protocol buffer message class that parser should parse.
    input_bytes: A buffered input.

  Example usage:
    while True:
      msg = proto.parse_length_prefixed(message_class, input_bytes)
      if msg is None:
        break
      ...

  Returns:
    A parsed message if successful. None if input_bytes is at EOF.
  """
  size = decoder._DecodeVarint(input_bytes)
  if size is None:
    # It is the end of buffered input. See example usage in the
    # API description.
    return None

  message = message_class()

  if size == 0:
    return message

  parsed_size = message.ParseFromString(input_bytes.read(size))
  if parsed_size != size:
    raise ValueError(
        'Truncated message or non-buffered input_bytes: '
        'Expected {0} bytes but only {1} bytes parsed for '
        '{2}.'.format(size, parsed_size, message.DESCRIPTOR.name)
    )
  return message
