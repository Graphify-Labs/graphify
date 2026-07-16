# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Provides a container for DescriptorProtos."""

__author__ = 'matthewtoia@google.com (Matt Toia)'

import warnings


class Error(Exception):
  pass


class DescriptorDatabaseConflictingDefinitionError(Error):
  """Raised when a proto is added with the same name & different descriptor."""


class DescriptorDatabase(object):
  """A container accepting FileDescriptorProtos and maps DescriptorProtos."""

  def __init__(self):
    self._file_desc_protos_by_file = {}
    self._file_desc_protos_by_symbol = {}

  def Add(self, file_desc_proto):
    """Adds the FileDescriptorProto and its types to this database.

    Args:
      file_desc_proto: The FileDescriptorProto to add.
    Raises:
      DescriptorDatabaseConflictingDefinitionError: if an attempt is made to
        add a proto with the same name but different definition than an
        existing proto in the database.
    """
    proto_name = file_desc_proto.name
    if proto_name not in self._file_desc_protos_by_file:
      self._file_desc_protos_by_file[proto_name] = file_desc_proto
    elif self._file_desc_protos_by_file[proto_name] != file_desc_proto:
      raise DescriptorDatabaseConflictingDefinitionError(
          '%s already added, but with different descriptor.' % proto_name)
    else:
      return

    # Add all the top-level descriptors to the index.
    package = file_desc_proto.package
    for message in file_desc_proto.message_type:
      for name in _ExtractSymbols(message, package):
        self._AddSymbol(name, file_desc_proto)
    for enum in file_desc_proto.enum_type:
      self._AddSymbol(('.'.join((package, enum.name))), file_desc_proto)
      for enum_value in enum.value:
        self._file_desc_protos_by_symbol[
            '.'.join((package, enum_value.name))] = file_desc_proto
    for extension in file_desc_proto.extension:
      self._AddSymbol(('.'.join((package, extension.name))), file_desc_proto)
    for service in file_desc_proto.service:
      self._AddSymbol(('.'.join((package, service.name))), file_desc_proto)

  def FindFileByName(self, name):
    """Finds the file descriptor proto by file name.

    Typically the file name is a relative path ending to a .proto file. The
    proto with the given name will have to have been added to this database
    using the Add method or else an error will be raised.

    Args:
      name: The file name to find.

    Returns:
      The file descriptor proto matching the name.

    Raises:
      KeyError if no file by the given name was added.
    """

    return self._file_desc_protos_by_file[name]

  def FindFileContainingSymbol(self, symbol):
    """Finds the file descriptor proto containing the specified symbol.

    The symbol should be a fully qualified name including the file descriptor's
    package and any containing messages. Some examples:

    'some.package.name.Message'
    'some.package.name.Message.NestedEnum'
    'some.package.name.Message.some_field'

    The file descriptor proto containing the specified symbol must be added to
    this database using the Add method or else an error will be raised.

    Args:
      symbol: The fully qualified symbol name.

    Returns:
      The file descriptor proto containing the symbol.

    Raises:
      KeyError if no file contains the specified symbol.
    """
    try:
      return self._file_desc_protos_by_symbol[symbol]
    except KeyError:
      # Fields, enum values, and nested extensions are not in
      # _file_desc_protos_by_symbol. Try to find the top level
      # descriptor. Non-existent nested symbol under a valid top level
      # descriptor can also be found. The behavior is the same with
      # protobuf C++.
      top_level, _, _ = symbol.rpartition('.')
      try:
        return self._file_desc_protos_by_symbol[top_level]
      except KeyError:
        # Raise the original symbol as a KeyError for better diagnostics.
        raise KeyError(symbol)

  def FindFileContainingExtension(self, extendee_name, extension_number):
    # TODO: implement this API.
    return None

  def FindAllExtensionNumbers(self, extendee_name):
    # TODO: implement this API.
    return []

  def _AddSymbol(self, name, file_desc_proto):
    if name in self._file_desc_protos_by_symbol:
      warn_msg = ('Conflict register for file "' + file_desc_proto.name +
                  '": ' + name +
                  ' is already defined in file "' +
                  self._file_desc_protos_by_symbol[name].name + '"')
      warnings.warn(warn_msg, RuntimeWarning)
    self._file_desc_protos_by_symbol[name] = file_desc_proto


def _ExtractSymbols(desc_proto, package):
  """Pulls out all the symbols from a descriptor proto.

  Args:
    desc_proto: The proto to extract symbols from.
    package: The package containing the descriptor type.

  Yields:
    The fully qualified name found in the descriptor.
  """
  message_name = package + '.' + desc_proto.name if package else desc_proto.name
  yield message_name
  for nested_type in desc_proto.nested_type:
    for symbol in _ExtractSymbols(nested_type, message_name):
      yield symbol
  for enum_type in desc_proto.enum_type:
    yield '.'.join((message_name, enum_type.name))
