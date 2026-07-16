# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Contains the Any helper APIs."""

from typing import Optional

from google.protobuf import descriptor
from google.protobuf.message import Message

from google.protobuf.any_pb2 import Any


def pack(
    msg: Message,
    type_url_prefix: Optional[str] = 'type.googleapis.com/',
    deterministic: Optional[bool] = None,
) -> Any:
  any_msg = Any()
  any_msg.Pack(
      msg=msg, type_url_prefix=type_url_prefix, deterministic=deterministic
  )
  return any_msg


def unpack(any_msg: Any, msg: Message) -> bool:
  return any_msg.Unpack(msg=msg)


def type_name(any_msg: Any) -> str:
  return any_msg.TypeName()


def is_type(any_msg: Any, des: descriptor.Descriptor) -> bool:
  return any_msg.Is(des)
