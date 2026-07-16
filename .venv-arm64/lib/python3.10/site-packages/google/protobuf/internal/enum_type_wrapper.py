# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""A simple wrapper around enum types to expose utility functions.

Instances are created as properties with the same name as the enum they wrap
on proto classes.  For usage, see:
  reflection_test.py
"""

import sys

__author__ = 'rabsatt@google.com (Kevin Rabsatt)'


class EnumTypeWrapper(object):
  """A utility for finding the names of enum values."""

  DESCRIPTOR = None

  # This is a type alias, which mypy typing stubs can type as
  # a genericized parameter constrained to an int, allowing subclasses
  # to be typed with more constraint in .pyi stubs
  # Eg.
  # def MyGeneratedEnum(Message):
  #   ValueType = NewType('ValueType', int)
  #   def Name(self, number: MyGeneratedEnum.ValueType) -> str
  ValueType = int

  def __init__(self, enum_type):
    """Inits EnumTypeWrapper with an EnumDescriptor."""
    self._enum_type = enum_type
    self.DESCRIPTOR = enum_type  # pylint: disable=invalid-name

  def Name(self, number):  # pylint: disable=invalid-name
    """Returns a string containing the name of an enum value."""
    try:
      return self._enum_type.values_by_number[number].name
    except KeyError:
      pass  # fall out to break exception chaining

    if not isinstance(number, int):
      raise TypeError(
          'Enum value for {} must be an int, but got {} {!r}.'.format(
              self._enum_type.name, type(number), number))
    else:
      # repr here to handle the odd case when you pass in a boolean.
      raise ValueError('Enum {} has no name defined for value {!r}'.format(
          self._enum_type.name, number))

  def Value(self, name):  # pylint: disable=invalid-name
    """Returns the value corresponding to the given enum name."""
    try:
      return self._enum_type.values_by_name[name].number
    except KeyError:
      pass  # fall out to break exception chaining
    raise ValueError('Enum {} has no value defined for name {!r}'.format(
        self._enum_type.name, name))

  def keys(self):
    """Return a list of the string names in the enum.

    Returns:
      A list of strs, in the order they were defined in the .proto file.
    """

    return [value_descriptor.name
            for value_descriptor in self._enum_type.values]

  def values(self):
    """Return a list of the integer values in the enum.

    Returns:
      A list of ints, in the order they were defined in the .proto file.
    """

    return [value_descriptor.number
            for value_descriptor in self._enum_type.values]

  def items(self):
    """Return a list of the (name, value) pairs of the enum.

    Returns:
      A list of (str, int) pairs, in the order they were defined
      in the .proto file.
    """
    return [(value_descriptor.name, value_descriptor.number)
            for value_descriptor in self._enum_type.values]

  def __getattr__(self, name):
    """Returns the value corresponding to the given enum name."""
    try:
      return super(
          EnumTypeWrapper,
          self).__getattribute__('_enum_type').values_by_name[name].number
    except KeyError:
      pass  # fall out to break exception chaining
    raise AttributeError('Enum {} has no value defined for name {!r}'.format(
        self._enum_type.name, name))

  def __or__(self, other):
    """Returns the union type of self and other."""
    if sys.version_info >= (3, 10):
      return type(self) | other
    else:
      raise NotImplementedError(
          'You may not use | on EnumTypes (or classes) below python 3.10'
      )
