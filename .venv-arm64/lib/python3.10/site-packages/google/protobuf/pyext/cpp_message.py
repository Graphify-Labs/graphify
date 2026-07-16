# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Protocol message implementation hooks for C++ implementation.

Contains helper functions used to create protocol message classes from
Descriptor objects at runtime backed by the protocol buffer C++ API.
"""

__author__ = 'tibell@google.com (Johan Tibell)'

from google.protobuf.internal import api_implementation


# pylint: disable=protected-access
_message = api_implementation._c_module
# TODO: Remove this import after fix api_implementation
if _message is None:
  from google.protobuf.pyext import _message


class GeneratedProtocolMessageType(_message.MessageMeta):

  """Metaclass for protocol message classes created at runtime from Descriptors.

  The protocol compiler currently uses this metaclass to create protocol
  message classes at runtime.  Clients can also manually create their own
  classes at runtime, as in this example:

  mydescriptor = Descriptor(.....)
  factory = symbol_database.Default()
  factory.pool.AddDescriptor(mydescriptor)
  MyProtoClass = message_factory.GetMessageClass(mydescriptor)
  myproto_instance = MyProtoClass()
  myproto.foo_field = 23
  ...

  The above example will not work for nested types. If you wish to include them,
  use reflection.MakeClass() instead of manually instantiating the class in
  order to create the appropriate class structure.
  """

  # Must be consistent with the protocol-compiler code in
  # proto2/compiler/internal/generator.*.
  _DESCRIPTOR_KEY = 'DESCRIPTOR'
