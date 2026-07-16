# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Contains the Nextgen Pythonic Protobuf JSON APIs."""

from typing import Optional, Type

from google.protobuf.message import Message
from google.protobuf.descriptor_pool import DescriptorPool
from google.protobuf import json_format

def serialize(
    message: Message,
    always_print_fields_with_no_presence: bool=False,
    preserving_proto_field_name: bool=False,
    use_integers_for_enums: bool=False,
    descriptor_pool: Optional[DescriptorPool]=None,
    float_precision: int=None,
) -> dict:
  """Converts protobuf message to a dictionary.

  When the dictionary is encoded to JSON, it conforms to proto3 JSON spec.

  Args:
    message: The protocol buffers message instance to serialize.
    always_print_fields_with_no_presence: If True, fields without
      presence (implicit presence scalars, repeated fields, and map fields) will
      always be serialized. Any field that supports presence is not affected by
      this option (including singular message fields and oneof fields).
    preserving_proto_field_name: If True, use the original proto field names as
      defined in the .proto file. If False, convert the field names to
      lowerCamelCase.
    use_integers_for_enums: If true, print integers instead of enum names.
    descriptor_pool: A Descriptor Pool for resolving types. If None use the
      default.
    float_precision: If set, use this to specify float field valid digits.

  Returns:
    A dict representation of the protocol buffer message.
  """
  return json_format.MessageToDict(
      message,
      always_print_fields_with_no_presence=always_print_fields_with_no_presence,
      preserving_proto_field_name=preserving_proto_field_name,
      use_integers_for_enums=use_integers_for_enums,
      float_precision=float_precision,
  )

def parse(
    message_class: Type[Message],
    js_dict: dict,
    ignore_unknown_fields: bool=False,
    descriptor_pool: Optional[DescriptorPool]=None,
    max_recursion_depth: int=100
) -> Message:
  """Parses a JSON dictionary representation into a message.

  Args:
    message_class: The message meta class.
    js_dict: Dict representation of a JSON message.
    ignore_unknown_fields: If True, do not raise errors for unknown fields.
    descriptor_pool: A Descriptor Pool for resolving types. If None use the
      default.
    max_recursion_depth: max recursion depth of JSON message to be deserialized.
      JSON messages over this depth will fail to be deserialized. Default value
      is 100.

  Returns:
    A new message passed from json_dict.
  """
  new_message = message_class()
  json_format.ParseDict(
      js_dict=js_dict,
      message=new_message,
      ignore_unknown_fields=ignore_unknown_fields,
      descriptor_pool=descriptor_pool,
      max_recursion_depth=max_recursion_depth,
  )
  return new_message
