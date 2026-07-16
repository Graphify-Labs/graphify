# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""A database of Python protocol buffer generated symbols.

SymbolDatabase is the MessageFactory for messages generated at compile time,
and makes it easy to create new instances of a registered type, given only the
type's protocol buffer symbol name.

Example usage::

  db = symbol_database.SymbolDatabase()

  # Register symbols of interest, from one or multiple files.
  db.RegisterFileDescriptor(my_proto_pb2.DESCRIPTOR)
  db.RegisterMessage(my_proto_pb2.MyMessage)
  db.RegisterEnumDescriptor(my_proto_pb2.MyEnum.DESCRIPTOR)

  # The database can be used as a MessageFactory, to generate types based on
  # their name:
  types = db.GetMessages(['my_proto.proto'])
  my_message_instance = types['MyMessage']()

  # The database's underlying descriptor pool can be queried, so it's not
  # necessary to know a type's filename to be able to generate it:
  filename = db.pool.FindFileContainingSymbol('MyMessage')
  my_message_instance = db.GetMessages([filename])['MyMessage']()

  # This functionality is also provided directly via a convenience method:
  my_message_instance = db.GetSymbol('MyMessage')()
"""

import warnings

from google.protobuf.internal import api_implementation
from google.protobuf import descriptor_pool
from google.protobuf import message_factory


class SymbolDatabase():
  """A database of Python generated symbols."""

  # local cache of registered classes.
  _classes = {}

  def __init__(self, pool=None):
    """Initializes a new SymbolDatabase."""
    self.pool = pool or descriptor_pool.DescriptorPool()

  def GetPrototype(self, descriptor):
    warnings.warn('SymbolDatabase.GetPrototype() is deprecated. Please '
                  'use message_factory.GetMessageClass() instead. '
                  'SymbolDatabase.GetPrototype() will be removed soon.')
    return message_factory.GetMessageClass(descriptor)

  def CreatePrototype(self, descriptor):
    warnings.warn('Directly call CreatePrototype() is wrong. Please use '
                  'message_factory.GetMessageClass() instead. '
                  'SymbolDatabase.CreatePrototype() will be removed soon.')
    return message_factory._InternalCreateMessageClass(descriptor)

  def GetMessages(self, files):
    warnings.warn('SymbolDatabase.GetMessages() is deprecated. Please use '
                  'message_factory.GetMessageClassedForFiles() instead. '
                  'SymbolDatabase.GetMessages() will be removed soon.')
    return message_factory.GetMessageClassedForFiles(files, self.pool)

  def RegisterMessage(self, message):
    """Registers the given message type in the local database.

    Calls to GetSymbol() and GetMessages() will return messages registered here.

    Args:
      message: A :class:`google.protobuf.message.Message` subclass (or
        instance); its descriptor will be registered.

    Returns:
      The provided message.
    """

    desc = message.DESCRIPTOR
    self._classes[desc] = message
    self.RegisterMessageDescriptor(desc)
    return message

  def RegisterMessageDescriptor(self, message_descriptor):
    """Registers the given message descriptor in the local database.

    Args:
      message_descriptor (Descriptor): the message descriptor to add.
    """
    if api_implementation.Type() == 'python':
      # pylint: disable=protected-access
      self.pool._AddDescriptor(message_descriptor)

  def RegisterEnumDescriptor(self, enum_descriptor):
    """Registers the given enum descriptor in the local database.

    Args:
      enum_descriptor (EnumDescriptor): The enum descriptor to register.

    Returns:
      EnumDescriptor: The provided descriptor.
    """
    if api_implementation.Type() == 'python':
      # pylint: disable=protected-access
      self.pool._AddEnumDescriptor(enum_descriptor)
    return enum_descriptor

  def RegisterServiceDescriptor(self, service_descriptor):
    """Registers the given service descriptor in the local database.

    Args:
      service_descriptor (ServiceDescriptor): the service descriptor to
        register.
    """
    if api_implementation.Type() == 'python':
      # pylint: disable=protected-access
      self.pool._AddServiceDescriptor(service_descriptor)

  def RegisterFileDescriptor(self, file_descriptor):
    """Registers the given file descriptor in the local database.

    Args:
      file_descriptor (FileDescriptor): The file descriptor to register.
    """
    if api_implementation.Type() == 'python':
      # pylint: disable=protected-access
      self.pool._InternalAddFileDescriptor(file_descriptor)

  def GetSymbol(self, symbol):
    """Tries to find a symbol in the local database.

    Currently, this method only returns message.Message instances, however, if
    may be extended in future to support other symbol types.

    Args:
      symbol (str): a protocol buffer symbol.

    Returns:
      A Python class corresponding to the symbol.

    Raises:
      KeyError: if the symbol could not be found.
    """

    return self._classes[self.pool.FindMessageTypeByName(symbol)]

  def GetMessages(self, files):
    # TODO: Fix the differences with MessageFactory.
    """Gets all registered messages from a specified file.

    Only messages already created and registered will be returned; (this is the
    case for imported _pb2 modules)
    But unlike MessageFactory, this version also returns already defined nested
    messages, but does not register any message extensions.

    Args:
      files (list[str]): The file names to extract messages from.

    Returns:
      A dictionary mapping proto names to the message classes.

    Raises:
      KeyError: if a file could not be found.
    """

    def _GetAllMessages(desc):
      """Walk a message Descriptor and recursively yields all message names."""
      yield desc
      for msg_desc in desc.nested_types:
        for nested_desc in _GetAllMessages(msg_desc):
          yield nested_desc

    result = {}
    for file_name in files:
      file_desc = self.pool.FindFileByName(file_name)
      for msg_desc in file_desc.message_types_by_name.values():
        for desc in _GetAllMessages(msg_desc):
          try:
            result[desc.full_name] = self._classes[desc]
          except KeyError:
            # This descriptor has no registered class, skip it.
            pass
    return result


_DEFAULT = SymbolDatabase(pool=descriptor_pool.Default())


def Default():
  """Returns the default SymbolDatabase."""
  return _DEFAULT
