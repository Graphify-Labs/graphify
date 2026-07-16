# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Descriptors essentially contain exactly the information found in a .proto
file, in types that make this information accessible in Python.
"""

__author__ = 'robinson@google.com (Will Robinson)'

import abc
import binascii
import os
import threading
import warnings

from google.protobuf.internal import api_implementation

_USE_C_DESCRIPTORS = False
if api_implementation.Type() != 'python':
  # pylint: disable=protected-access
  _message = api_implementation._c_module
  # TODO: Remove this import after fix api_implementation
  if _message is None:
    from google.protobuf.pyext import _message
  _USE_C_DESCRIPTORS = True


class Error(Exception):
  """Base error for this module."""


class TypeTransformationError(Error):
  """Error transforming between python proto type and corresponding C++ type."""


if _USE_C_DESCRIPTORS:
  # This metaclass allows to override the behavior of code like
  #     isinstance(my_descriptor, FieldDescriptor)
  # and make it return True when the descriptor is an instance of the extension
  # type written in C++.
  class DescriptorMetaclass(type):

    def __instancecheck__(cls, obj):
      if super(DescriptorMetaclass, cls).__instancecheck__(obj):
        return True
      if isinstance(obj, cls._C_DESCRIPTOR_CLASS):
        return True
      return False
else:
  # The standard metaclass; nothing changes.
  DescriptorMetaclass = abc.ABCMeta


class _Lock(object):
  """Wrapper class of threading.Lock(), which is allowed by 'with'."""

  def __new__(cls):
    self = object.__new__(cls)
    self._lock = threading.Lock()  # pylint: disable=protected-access
    return self

  def __enter__(self):
    self._lock.acquire()

  def __exit__(self, exc_type, exc_value, exc_tb):
    self._lock.release()


_lock = threading.Lock()


def _Deprecated(name):
  if _Deprecated.count > 0:
    _Deprecated.count -= 1
    warnings.warn(
        'Call to deprecated create function %s(). Note: Create unlinked '
        'descriptors is going to go away. Please use get/find descriptors from '
        'generated code or query the descriptor_pool.'
        % name,
        category=DeprecationWarning, stacklevel=3)

# These must match the values in descriptor.proto, but we can't use them
# directly because we sometimes need to reference them in feature helpers
# below *during* the build of descriptor.proto.
_FEATURESET_MESSAGE_ENCODING_DELIMITED = 2
_FEATURESET_FIELD_PRESENCE_IMPLICIT = 2
_FEATURESET_FIELD_PRESENCE_LEGACY_REQUIRED = 3
_FEATURESET_REPEATED_FIELD_ENCODING_PACKED = 1
_FEATURESET_ENUM_TYPE_CLOSED = 2

# Deprecated warnings will print 100 times at most which should be enough for
# users to notice and do not cause timeout.
_Deprecated.count = 100


_internal_create_key = object()


class DescriptorBase(metaclass=DescriptorMetaclass):

  """Descriptors base class.

  This class is the base of all descriptor classes. It provides common options
  related functionality.

  Attributes:
    has_options:  True if the descriptor has non-default options.  Usually it is
      not necessary to read this -- just call GetOptions() which will happily
      return the default instance.  However, it's sometimes useful for
      efficiency, and also useful inside the protobuf implementation to avoid
      some bootstrapping issues.
    file (FileDescriptor): Reference to file info.
  """

  if _USE_C_DESCRIPTORS:
    # The class, or tuple of classes, that are considered as "virtual
    # subclasses" of this descriptor class.
    _C_DESCRIPTOR_CLASS = ()

  def __init__(self, file, options, serialized_options, options_class_name):
    """Initialize the descriptor given its options message and the name of the
    class of the options message. The name of the class is required in case
    the options message is None and has to be created.
    """
    self._features = None
    self.file = file
    self._original_options = options
    # These two fields are duplicated as a compatibility shim for old gencode
    # that resets them.  In 26.x (cl/580304039) we renamed _options to,
    # _loaded_options breaking backwards compatibility.
    self._options = self._loaded_options = None
    self._options_class_name = options_class_name
    self._serialized_options = serialized_options

    # Does this descriptor have non-default options?
    self.has_options = (self._original_options is not None) or (
        self._serialized_options is not None
    )

  @property
  @abc.abstractmethod
  def _parent(self):
    pass

  def _InferLegacyFeatures(self, edition, options, features):
    """Infers features from proto2/proto3 syntax so that editions logic can be used everywhere.

    Args:
      edition: The edition to infer features for.
      options: The options for this descriptor that are being processed.
      features: The feature set object to modify with inferred features.
    """
    pass

  def _GetFeatures(self):
    if not self._features:
      self._LazyLoadOptions()
    return self._features

  def _ResolveFeatures(self, edition, raw_options):
    """Resolves features from the raw options of this descriptor.

    Args:
      edition: The edition to use for feature defaults.
      raw_options: The options for this descriptor that are being processed.

    Returns:
      A fully resolved feature set for making runtime decisions.
    """
    # pylint: disable=g-import-not-at-top
    from google.protobuf import descriptor_pb2

    if self._parent:
      features = descriptor_pb2.FeatureSet()
      features.CopyFrom(self._parent._GetFeatures())
    else:
      features = self.file.pool._CreateDefaultFeatures(edition)
    unresolved = descriptor_pb2.FeatureSet()
    unresolved.CopyFrom(raw_options.features)
    self._InferLegacyFeatures(edition, raw_options, unresolved)
    features.MergeFrom(unresolved)

    # Use the feature cache to reduce memory bloat.
    return self.file.pool._InternFeatures(features)

  def _LazyLoadOptions(self):
    """Lazily initializes descriptor options towards the end of the build."""
    if self._options and self._loaded_options == self._options:
      # If neither has been reset by gencode, use the cache.
      return

    # pylint: disable=g-import-not-at-top
    from google.protobuf import descriptor_pb2

    if not hasattr(descriptor_pb2, self._options_class_name):
      raise RuntimeError(
          'Unknown options class name %s!' % self._options_class_name
      )
    options_class = getattr(descriptor_pb2, self._options_class_name)
    features = None
    edition = self.file._edition

    if not self.has_options:
      if not self._features:
        features = self._ResolveFeatures(
            descriptor_pb2.Edition.Value(edition), options_class()
        )
      with _lock:
        self._options = self._loaded_options = options_class()
        if not self._features:
          self._features = features
    else:
      if not self._serialized_options:
        options = self._original_options
      else:
        options = _ParseOptions(options_class(), self._serialized_options)

      if not self._features:
        features = self._ResolveFeatures(
            descriptor_pb2.Edition.Value(edition), options
        )
      with _lock:
        self._options = self._loaded_options = options
        if not self._features:
          self._features = features
        if options.HasField('features'):
          options.ClearField('features')
          if not options.SerializeToString():
            self._options = self._loaded_options = options_class()
            self.has_options = False

  def GetOptions(self):
    """Retrieves descriptor options.

    Returns:
      The options set on this descriptor.
    """
    # If either has been reset by gencode, reload options.
    if not self._options or not self._loaded_options:
      self._LazyLoadOptions()
    return self._options


class _NestedDescriptorBase(DescriptorBase):
  """Common class for descriptors that can be nested."""

  def __init__(self, options, options_class_name, name, full_name,
               file, containing_type, serialized_start=None,
               serialized_end=None, serialized_options=None):
    """Constructor.

    Args:
      options: Protocol message options or None to use default message options.
      options_class_name (str): The class name of the above options.
      name (str): Name of this protocol message type.
      full_name (str): Fully-qualified name of this protocol message type, which
        will include protocol "package" name and the name of any enclosing
        types.
      containing_type: if provided, this is a nested descriptor, with this
        descriptor as parent, otherwise None.
      serialized_start: The start index (inclusive) in block in the
        file.serialized_pb that describes this descriptor.
      serialized_end: The end index (exclusive) in block in the
        file.serialized_pb that describes this descriptor.
      serialized_options: Protocol message serialized options or None.
    """
    super(_NestedDescriptorBase, self).__init__(
        file, options, serialized_options, options_class_name
    )

    self.name = name
    # TODO: Add function to calculate full_name instead of having it in
    #             memory?
    self.full_name = full_name
    self.containing_type = containing_type

    self._serialized_start = serialized_start
    self._serialized_end = serialized_end

  def CopyToProto(self, proto):
    """Copies this to the matching proto in descriptor_pb2.

    Args:
      proto: An empty proto instance from descriptor_pb2.

    Raises:
      Error: If self couldn't be serialized, due to to few constructor
        arguments.
    """
    if (self.file is not None and
        self._serialized_start is not None and
        self._serialized_end is not None):
      proto.ParseFromString(self.file.serialized_pb[
          self._serialized_start:self._serialized_end])
    else:
      raise Error('Descriptor does not contain serialization.')


class Descriptor(_NestedDescriptorBase):

  """Descriptor for a protocol message type.

  Attributes:
      name (str): Name of this protocol message type.
      full_name (str): Fully-qualified name of this protocol message type,
          which will include protocol "package" name and the name of any
          enclosing types.
      containing_type (Descriptor): Reference to the descriptor of the type
          containing us, or None if this is top-level.
      fields (list[FieldDescriptor]): Field descriptors for all fields in
          this type.
      fields_by_number (dict(int, FieldDescriptor)): Same
          :class:`FieldDescriptor` objects as in :attr:`fields`, but indexed
          by "number" attribute in each FieldDescriptor.
      fields_by_name (dict(str, FieldDescriptor)): Same
          :class:`FieldDescriptor` objects as in :attr:`fields`, but indexed by
          "name" attribute in each :class:`FieldDescriptor`.
      nested_types (list[Descriptor]): Descriptor references
          for all protocol message types nested within this one.
      nested_types_by_name (dict(str, Descriptor)): Same Descriptor
          objects as in :attr:`nested_types`, but indexed by "name" attribute
          in each Descriptor.
      enum_types (list[EnumDescriptor]): :class:`EnumDescriptor` references
          for all enums contained within this type.
      enum_types_by_name (dict(str, EnumDescriptor)): Same
          :class:`EnumDescriptor` objects as in :attr:`enum_types`, but
          indexed by "name" attribute in each EnumDescriptor.
      enum_values_by_name (dict(str, EnumValueDescriptor)): Dict mapping
          from enum value name to :class:`EnumValueDescriptor` for that value.
      extensions (list[FieldDescriptor]): All extensions defined directly
          within this message type (NOT within a nested type).
      extensions_by_name (dict(str, FieldDescriptor)): Same FieldDescriptor
          objects as :attr:`extensions`, but indexed by "name" attribute of each
          FieldDescriptor.
      is_extendable (bool):  Does this type define any extension ranges?
      oneofs (list[OneofDescriptor]): The list of descriptors for oneof fields
          in this message.
      oneofs_by_name (dict(str, OneofDescriptor)): Same objects as in
          :attr:`oneofs`, but indexed by "name" attribute.
      file (FileDescriptor): Reference to file descriptor.
      is_map_entry: If the message type is a map entry.

  """

  if _USE_C_DESCRIPTORS:
    _C_DESCRIPTOR_CLASS = _message.Descriptor

    def __new__(
        cls,
        name=None,
        full_name=None,
        filename=None,
        containing_type=None,
        fields=None,
        nested_types=None,
        enum_types=None,
        extensions=None,
        options=None,
        serialized_options=None,
        is_extendable=True,
        extension_ranges=None,
        oneofs=None,
        file=None,  # pylint: disable=redefined-builtin
        serialized_start=None,
        serialized_end=None,
        syntax=None,
        is_map_entry=False,
        create_key=None):
      _message.Message._CheckCalledFromGeneratedFile()
      return _message.default_pool.FindMessageTypeByName(full_name)

  # NOTE: The file argument redefining a builtin is nothing we can
  # fix right now since we don't know how many clients already rely on the
  # name of the argument.
  def __init__(self, name, full_name, filename, containing_type, fields,
               nested_types, enum_types, extensions, options=None,
               serialized_options=None,
               is_extendable=True, extension_ranges=None, oneofs=None,
               file=None, serialized_start=None, serialized_end=None,  # pylint: disable=redefined-builtin
               syntax=None, is_map_entry=False, create_key=None):
    """Arguments to __init__() are as described in the description
    of Descriptor fields above.

    Note that filename is an obsolete argument, that is not used anymore.
    Please use file.name to access this as an attribute.
    """
    if create_key is not _internal_create_key:
      _Deprecated('Descriptor')

    super(Descriptor, self).__init__(
        options, 'MessageOptions', name, full_name, file,
        containing_type, serialized_start=serialized_start,
        serialized_end=serialized_end, serialized_options=serialized_options)

    # We have fields in addition to fields_by_name and fields_by_number,
    # so that:
    #   1. Clients can index fields by "order in which they're listed."
    #   2. Clients can easily iterate over all fields with the terse
    #      syntax: for f in descriptor.fields: ...
    self.fields = fields
    for field in self.fields:
      field.containing_type = self
      field.file = file
    self.fields_by_number = dict((f.number, f) for f in fields)
    self.fields_by_name = dict((f.name, f) for f in fields)
    self._fields_by_camelcase_name = None

    self.nested_types = nested_types
    for nested_type in nested_types:
      nested_type.containing_type = self
    self.nested_types_by_name = dict((t.name, t) for t in nested_types)

    self.enum_types = enum_types
    for enum_type in self.enum_types:
      enum_type.containing_type = self
    self.enum_types_by_name = dict((t.name, t) for t in enum_types)
    self.enum_values_by_name = dict(
        (v.name, v) for t in enum_types for v in t.values)

    self.extensions = extensions
    for extension in self.extensions:
      extension.extension_scope = self
    self.extensions_by_name = dict((f.name, f) for f in extensions)
    self.is_extendable = is_extendable
    self.extension_ranges = extension_ranges
    self.oneofs = oneofs if oneofs is not None else []
    self.oneofs_by_name = dict((o.name, o) for o in self.oneofs)
    for oneof in self.oneofs:
      oneof.containing_type = self
      oneof.file = file
    self._is_map_entry = is_map_entry

  @property
  def _parent(self):
    return self.containing_type or self.file

  @property
  def fields_by_camelcase_name(self):
    """Same FieldDescriptor objects as in :attr:`fields`, but indexed by
    :attr:`FieldDescriptor.camelcase_name`.
    """
    if self._fields_by_camelcase_name is None:
      self._fields_by_camelcase_name = dict(
          (f.camelcase_name, f) for f in self.fields)
    return self._fields_by_camelcase_name

  def EnumValueName(self, enum, value):
    """Returns the string name of an enum value.

    This is just a small helper method to simplify a common operation.

    Args:
      enum: string name of the Enum.
      value: int, value of the enum.

    Returns:
      string name of the enum value.

    Raises:
      KeyError if either the Enum doesn't exist or the value is not a valid
        value for the enum.
    """
    return self.enum_types_by_name[enum].values_by_number[value].name

  def CopyToProto(self, proto):
    """Copies this to a descriptor_pb2.DescriptorProto.

    Args:
      proto: An empty descriptor_pb2.DescriptorProto.
    """
    # This function is overridden to give a better doc comment.
    super(Descriptor, self).CopyToProto(proto)


# TODO: We should have aggressive checking here,
# for example:
#   * If you specify a repeated field, you should not be allowed
#     to specify a default value.
#   * [Other examples here as needed].
#
# TODO: for this and other *Descriptor classes, we
# might also want to lock things down aggressively (e.g.,
# prevent clients from setting the attributes).  Having
# stronger invariants here in general will reduce the number
# of runtime checks we must do in reflection.py...
class FieldDescriptor(DescriptorBase):

  """Descriptor for a single field in a .proto file.

  Attributes:
    name (str): Name of this field, exactly as it appears in .proto.
    full_name (str): Name of this field, including containing scope.  This is
      particularly relevant for extensions.
    index (int): Dense, 0-indexed index giving the order that this
      field textually appears within its message in the .proto file.
    number (int): Tag number declared for this field in the .proto file.

    type (int): (One of the TYPE_* constants below) Declared type.
    cpp_type (int): (One of the CPPTYPE_* constants below) C++ type used to
      represent this field.

    label (int): (One of the LABEL_* constants below) Tells whether this
      field is optional, required, or repeated.
    has_default_value (bool): True if this field has a default value defined,
      otherwise false.
    default_value (Varies): Default value of this field.  Only
      meaningful for non-repeated scalar fields.  Repeated fields
      should always set this to [], and non-repeated composite
      fields should always set this to None.

    containing_type (Descriptor): Descriptor of the protocol message
      type that contains this field.  Set by the Descriptor constructor
      if we're passed into one.
      Somewhat confusingly, for extension fields, this is the
      descriptor of the EXTENDED message, not the descriptor
      of the message containing this field.  (See is_extension and
      extension_scope below).
    message_type (Descriptor): If a composite field, a descriptor
      of the message type contained in this field.  Otherwise, this is None.
    enum_type (EnumDescriptor): If this field contains an enum, a
      descriptor of that enum.  Otherwise, this is None.

    is_extension: True iff this describes an extension field.
    extension_scope (Descriptor): Only meaningful if is_extension is True.
      Gives the message that immediately contains this extension field.
      Will be None iff we're a top-level (file-level) extension field.

    options (descriptor_pb2.FieldOptions): Protocol message field options or
      None to use default field options.

    containing_oneof (OneofDescriptor): If the field is a member of a oneof
      union, contains its descriptor. Otherwise, None.

    file (FileDescriptor): Reference to file descriptor.
  """

  # Must be consistent with C++ FieldDescriptor::Type enum in
  # descriptor.h.
  #
  # TODO: Find a way to eliminate this repetition.
  TYPE_DOUBLE         = 1
  TYPE_FLOAT          = 2
  TYPE_INT64          = 3
  TYPE_UINT64         = 4
  TYPE_INT32          = 5
  TYPE_FIXED64        = 6
  TYPE_FIXED32        = 7
  TYPE_BOOL           = 8
  TYPE_STRING         = 9
  TYPE_GROUP          = 10
  TYPE_MESSAGE        = 11
  TYPE_BYTES          = 12
  TYPE_UINT32         = 13
  TYPE_ENUM           = 14
  TYPE_SFIXED32       = 15
  TYPE_SFIXED64       = 16
  TYPE_SINT32         = 17
  TYPE_SINT64         = 18
  MAX_TYPE            = 18

  # Must be consistent with C++ FieldDescriptor::CppType enum in
  # descriptor.h.
  #
  # TODO: Find a way to eliminate this repetition.
  CPPTYPE_INT32       = 1
  CPPTYPE_INT64       = 2
  CPPTYPE_UINT32      = 3
  CPPTYPE_UINT64      = 4
  CPPTYPE_DOUBLE      = 5
  CPPTYPE_FLOAT       = 6
  CPPTYPE_BOOL        = 7
  CPPTYPE_ENUM        = 8
  CPPTYPE_STRING      = 9
  CPPTYPE_MESSAGE     = 10
  MAX_CPPTYPE         = 10

  _PYTHON_TO_CPP_PROTO_TYPE_MAP = {
      TYPE_DOUBLE: CPPTYPE_DOUBLE,
      TYPE_FLOAT: CPPTYPE_FLOAT,
      TYPE_ENUM: CPPTYPE_ENUM,
      TYPE_INT64: CPPTYPE_INT64,
      TYPE_SINT64: CPPTYPE_INT64,
      TYPE_SFIXED64: CPPTYPE_INT64,
      TYPE_UINT64: CPPTYPE_UINT64,
      TYPE_FIXED64: CPPTYPE_UINT64,
      TYPE_INT32: CPPTYPE_INT32,
      TYPE_SFIXED32: CPPTYPE_INT32,
      TYPE_SINT32: CPPTYPE_INT32,
      TYPE_UINT32: CPPTYPE_UINT32,
      TYPE_FIXED32: CPPTYPE_UINT32,
      TYPE_BYTES: CPPTYPE_STRING,
      TYPE_STRING: CPPTYPE_STRING,
      TYPE_BOOL: CPPTYPE_BOOL,
      TYPE_MESSAGE: CPPTYPE_MESSAGE,
      TYPE_GROUP: CPPTYPE_MESSAGE
      }

  # Must be consistent with C++ FieldDescriptor::Label enum in
  # descriptor.h.
  #
  # TODO: Find a way to eliminate this repetition.
  LABEL_OPTIONAL      = 1
  LABEL_REQUIRED      = 2
  LABEL_REPEATED      = 3
  MAX_LABEL           = 3

  # Must be consistent with C++ constants kMaxNumber, kFirstReservedNumber,
  # and kLastReservedNumber in descriptor.h
  MAX_FIELD_NUMBER = (1 << 29) - 1
  FIRST_RESERVED_FIELD_NUMBER = 19000
  LAST_RESERVED_FIELD_NUMBER = 19999

  if _USE_C_DESCRIPTORS:
    _C_DESCRIPTOR_CLASS = _message.FieldDescriptor

    def __new__(cls, name, full_name, index, number, type, cpp_type, label,
                default_value, message_type, enum_type, containing_type,
                is_extension, extension_scope, options=None,
                serialized_options=None,
                has_default_value=True, containing_oneof=None, json_name=None,
                file=None, create_key=None):  # pylint: disable=redefined-builtin
      _message.Message._CheckCalledFromGeneratedFile()
      if is_extension:
        return _message.default_pool.FindExtensionByName(full_name)
      else:
        return _message.default_pool.FindFieldByName(full_name)

  def __init__(self, name, full_name, index, number, type, cpp_type, label,
               default_value, message_type, enum_type, containing_type,
               is_extension, extension_scope, options=None,
               serialized_options=None,
               has_default_value=True, containing_oneof=None, json_name=None,
               file=None, create_key=None):  # pylint: disable=redefined-builtin
    """The arguments are as described in the description of FieldDescriptor
    attributes above.

    Note that containing_type may be None, and may be set later if necessary
    (to deal with circular references between message types, for example).
    Likewise for extension_scope.
    """
    if create_key is not _internal_create_key:
      _Deprecated('FieldDescriptor')

    super(FieldDescriptor, self).__init__(
        file, options, serialized_options, 'FieldOptions'
    )
    self.name = name
    self.full_name = full_name
    self._camelcase_name = None
    if json_name is None:
      self.json_name = _ToJsonName(name)
    else:
      self.json_name = json_name
    self.index = index
    self.number = number
    self._type = type
    self.cpp_type = cpp_type
    self._label = label
    self.has_default_value = has_default_value
    self.default_value = default_value
    self.containing_type = containing_type
    self.message_type = message_type
    self.enum_type = enum_type
    self.is_extension = is_extension
    self.extension_scope = extension_scope
    self.containing_oneof = containing_oneof
    if api_implementation.Type() == 'python':
      self._cdescriptor = None
    else:
      if is_extension:
        self._cdescriptor = _message.default_pool.FindExtensionByName(full_name)
      else:
        self._cdescriptor = _message.default_pool.FindFieldByName(full_name)

  @property
  def _parent(self):
    if self.containing_oneof:
      return self.containing_oneof
    if self.is_extension:
      return self.extension_scope or self.file
    return self.containing_type

  def _InferLegacyFeatures(self, edition, options, features):
    # pylint: disable=g-import-not-at-top
    from google.protobuf import descriptor_pb2

    if edition >= descriptor_pb2.Edition.EDITION_2023:
      return

    if self._label == FieldDescriptor.LABEL_REQUIRED:
      features.field_presence = (
          descriptor_pb2.FeatureSet.FieldPresence.LEGACY_REQUIRED
      )

    if self._type == FieldDescriptor.TYPE_GROUP:
      features.message_encoding = (
          descriptor_pb2.FeatureSet.MessageEncoding.DELIMITED
      )

    if options.HasField('packed'):
      features.repeated_field_encoding = (
          descriptor_pb2.FeatureSet.RepeatedFieldEncoding.PACKED
          if options.packed
          else descriptor_pb2.FeatureSet.RepeatedFieldEncoding.EXPANDED
      )

  @property
  def type(self):
    if (
        self._GetFeatures().message_encoding
        == _FEATURESET_MESSAGE_ENCODING_DELIMITED
        and self.message_type
        and not self.message_type.GetOptions().map_entry
        and not self.containing_type.GetOptions().map_entry
    ):
      return FieldDescriptor.TYPE_GROUP
    return self._type

  @type.setter
  def type(self, val):
    self._type = val

  @property
  def label(self):
    if (
        self._GetFeatures().field_presence
        == _FEATURESET_FIELD_PRESENCE_LEGACY_REQUIRED
    ):
      return FieldDescriptor.LABEL_REQUIRED
    return self._label

  @property
  def camelcase_name(self):
    """Camelcase name of this field.

    Returns:
      str: the name in CamelCase.
    """
    if self._camelcase_name is None:
      self._camelcase_name = _ToCamelCase(self.name)
    return self._camelcase_name

  @property
  def has_presence(self):
    """Whether the field distinguishes between unpopulated and default values.

    Raises:
      RuntimeError: singular field that is not linked with message nor file.
    """
    if self.label == FieldDescriptor.LABEL_REPEATED:
      return False
    if (
        self.cpp_type == FieldDescriptor.CPPTYPE_MESSAGE
        or self.is_extension
        or self.containing_oneof
    ):
      return True

    return (
        self._GetFeatures().field_presence
        != _FEATURESET_FIELD_PRESENCE_IMPLICIT
    )

  @property
  def is_packed(self):
    """Returns if the field is packed."""
    if self.label != FieldDescriptor.LABEL_REPEATED:
      return False
    field_type = self.type
    if (field_type == FieldDescriptor.TYPE_STRING or
        field_type == FieldDescriptor.TYPE_GROUP or
        field_type == FieldDescriptor.TYPE_MESSAGE or
        field_type == FieldDescriptor.TYPE_BYTES):
      return False

    return (
        self._GetFeatures().repeated_field_encoding
        == _FEATURESET_REPEATED_FIELD_ENCODING_PACKED
    )

  @staticmethod
  def ProtoTypeToCppProtoType(proto_type):
    """Converts from a Python proto type to a C++ Proto Type.

    The Python ProtocolBuffer classes specify both the 'Python' datatype and the
    'C++' datatype - and they're not the same. This helper method should
    translate from one to another.

    Args:
      proto_type: the Python proto type (descriptor.FieldDescriptor.TYPE_*)
    Returns:
      int: descriptor.FieldDescriptor.CPPTYPE_*, the C++ type.
    Raises:
      TypeTransformationError: when the Python proto type isn't known.
    """
    try:
      return FieldDescriptor._PYTHON_TO_CPP_PROTO_TYPE_MAP[proto_type]
    except KeyError:
      raise TypeTransformationError('Unknown proto_type: %s' % proto_type)


class EnumDescriptor(_NestedDescriptorBase):

  """Descriptor for an enum defined in a .proto file.

  Attributes:
    name (str): Name of the enum type.
    full_name (str): Full name of the type, including package name
      and any enclosing type(s).

    values (list[EnumValueDescriptor]): List of the values
      in this enum.
    values_by_name (dict(str, EnumValueDescriptor)): Same as :attr:`values`,
      but indexed by the "name" field of each EnumValueDescriptor.
    values_by_number (dict(int, EnumValueDescriptor)): Same as :attr:`values`,
      but indexed by the "number" field of each EnumValueDescriptor.
    containing_type (Descriptor): Descriptor of the immediate containing
      type of this enum, or None if this is an enum defined at the
      top level in a .proto file.  Set by Descriptor's constructor
      if we're passed into one.
    file (FileDescriptor): Reference to file descriptor.
    options (descriptor_pb2.EnumOptions): Enum options message or
      None to use default enum options.
  """

  if _USE_C_DESCRIPTORS:
    _C_DESCRIPTOR_CLASS = _message.EnumDescriptor

    def __new__(cls, name, full_name, filename, values,
                containing_type=None, options=None,
                serialized_options=None, file=None,  # pylint: disable=redefined-builtin
                serialized_start=None, serialized_end=None, create_key=None):
      _message.Message._CheckCalledFromGeneratedFile()
      return _message.default_pool.FindEnumTypeByName(full_name)

  def __init__(self, name, full_name, filename, values,
               containing_type=None, options=None,
               serialized_options=None, file=None,  # pylint: disable=redefined-builtin
               serialized_start=None, serialized_end=None, create_key=None):
    """Arguments are as described in the attribute description above.

    Note that filename is an obsolete argument, that is not used anymore.
    Please use file.name to access this as an attribute.
    """
    if create_key is not _internal_create_key:
      _Deprecated('EnumDescriptor')

    super(EnumDescriptor, self).__init__(
        options, 'EnumOptions', name, full_name, file,
        containing_type, serialized_start=serialized_start,
        serialized_end=serialized_end, serialized_options=serialized_options)

    self.values = values
    for value in self.values:
      value.file = file
      value.type = self
    self.values_by_name = dict((v.name, v) for v in values)
    # Values are reversed to ensure that the first alias is retained.
    self.values_by_number = dict((v.number, v) for v in reversed(values))

  @property
  def _parent(self):
    return self.containing_type or self.file

  @property
  def is_closed(self):
    """Returns true whether this is a "closed" enum.

    This means that it:
    - Has a fixed set of values, rather than being equivalent to an int32.
    - Encountering values not in this set causes them to be treated as unknown
      fields.
    - The first value (i.e., the default) may be nonzero.

    WARNING: Some runtimes currently have a quirk where non-closed enums are
    treated as closed when used as the type of fields defined in a
    `syntax = proto2;` file. This quirk is not present in all runtimes; as of
    writing, we know that:

    - C++, Java, and C++-based Python share this quirk.
    - UPB and UPB-based Python do not.
    - PHP and Ruby treat all enums as open regardless of declaration.

    Care should be taken when using this function to respect the target
    runtime's enum handling quirks.
    """
    return self._GetFeatures().enum_type == _FEATURESET_ENUM_TYPE_CLOSED

  def CopyToProto(self, proto):
    """Copies this to a descriptor_pb2.EnumDescriptorProto.

    Args:
      proto (descriptor_pb2.EnumDescriptorProto): An empty descriptor proto.
    """
    # This function is overridden to give a better doc comment.
    super(EnumDescriptor, self).CopyToProto(proto)


class EnumValueDescriptor(DescriptorBase):

  """Descriptor for a single value within an enum.

  Attributes:
    name (str): Name of this value.
    index (int): Dense, 0-indexed index giving the order that this
      value appears textually within its enum in the .proto file.
    number (int): Actual number assigned to this enum value.
    type (EnumDescriptor): :class:`EnumDescriptor` to which this value
      belongs.  Set by :class:`EnumDescriptor`'s constructor if we're
      passed into one.
    options (descriptor_pb2.EnumValueOptions): Enum value options message or
      None to use default enum value options options.
  """

  if _USE_C_DESCRIPTORS:
    _C_DESCRIPTOR_CLASS = _message.EnumValueDescriptor

    def __new__(cls, name, index, number,
                type=None,  # pylint: disable=redefined-builtin
                options=None, serialized_options=None, create_key=None):
      _message.Message._CheckCalledFromGeneratedFile()
      # There is no way we can build a complete EnumValueDescriptor with the
      # given parameters (the name of the Enum is not known, for example).
      # Fortunately generated files just pass it to the EnumDescriptor()
      # constructor, which will ignore it, so returning None is good enough.
      return None

  def __init__(self, name, index, number,
               type=None,  # pylint: disable=redefined-builtin
               options=None, serialized_options=None, create_key=None):
    """Arguments are as described in the attribute description above."""
    if create_key is not _internal_create_key:
      _Deprecated('EnumValueDescriptor')

    super(EnumValueDescriptor, self).__init__(
        type.file if type else None,
        options,
        serialized_options,
        'EnumValueOptions',
    )
    self.name = name
    self.index = index
    self.number = number
    self.type = type

  @property
  def _parent(self):
    return self.type


class OneofDescriptor(DescriptorBase):
  """Descriptor for a oneof field.

  Attributes:
    name (str): Name of the oneof field.
    full_name (str): Full name of the oneof field, including package name.
    index (int): 0-based index giving the order of the oneof field inside
      its containing type.
    containing_type (Descriptor): :class:`Descriptor` of the protocol message
      type that contains this field.  Set by the :class:`Descriptor` constructor
      if we're passed into one.
    fields (list[FieldDescriptor]): The list of field descriptors this
      oneof can contain.
  """

  if _USE_C_DESCRIPTORS:
    _C_DESCRIPTOR_CLASS = _message.OneofDescriptor

    def __new__(
        cls, name, full_name, index, containing_type, fields, options=None,
        serialized_options=None, create_key=None):
      _message.Message._CheckCalledFromGeneratedFile()
      return _message.default_pool.FindOneofByName(full_name)

  def __init__(
      self, name, full_name, index, containing_type, fields, options=None,
      serialized_options=None, create_key=None):
    """Arguments are as described in the attribute description above."""
    if create_key is not _internal_create_key:
      _Deprecated('OneofDescriptor')

    super(OneofDescriptor, self).__init__(
        containing_type.file if containing_type else None,
        options,
        serialized_options,
        'OneofOptions',
    )
    self.name = name
    self.full_name = full_name
    self.index = index
    self.containing_type = containing_type
    self.fields = fields

  @property
  def _parent(self):
    return self.containing_type


class ServiceDescriptor(_NestedDescriptorBase):

  """Descriptor for a service.

  Attributes:
    name (str): Name of the service.
    full_name (str): Full name of the service, including package name.
    index (int): 0-indexed index giving the order that this services
      definition appears within the .proto file.
    methods (list[MethodDescriptor]): List of methods provided by this
      service.
    methods_by_name (dict(str, MethodDescriptor)): Same
      :class:`MethodDescriptor` objects as in :attr:`methods_by_name`, but
      indexed by "name" attribute in each :class:`MethodDescriptor`.
    options (descriptor_pb2.ServiceOptions): Service options message or
      None to use default service options.
    file (FileDescriptor): Reference to file info.
  """

  if _USE_C_DESCRIPTORS:
    _C_DESCRIPTOR_CLASS = _message.ServiceDescriptor

    def __new__(
        cls,
        name=None,
        full_name=None,
        index=None,
        methods=None,
        options=None,
        serialized_options=None,
        file=None,  # pylint: disable=redefined-builtin
        serialized_start=None,
        serialized_end=None,
        create_key=None):
      _message.Message._CheckCalledFromGeneratedFile()  # pylint: disable=protected-access
      return _message.default_pool.FindServiceByName(full_name)

  def __init__(self, name, full_name, index, methods, options=None,
               serialized_options=None, file=None,  # pylint: disable=redefined-builtin
               serialized_start=None, serialized_end=None, create_key=None):
    if create_key is not _internal_create_key:
      _Deprecated('ServiceDescriptor')

    super(ServiceDescriptor, self).__init__(
        options, 'ServiceOptions', name, full_name, file,
        None, serialized_start=serialized_start,
        serialized_end=serialized_end, serialized_options=serialized_options)
    self.index = index
    self.methods = methods
    self.methods_by_name = dict((m.name, m) for m in methods)
    # Set the containing service for each method in this service.
    for method in self.methods:
      method.file = self.file
      method.containing_service = self

  @property
  def _parent(self):
    return self.file

  def FindMethodByName(self, name):
    """Searches for the specified method, and returns its descriptor.

    Args:
      name (str): Name of the method.

    Returns:
      MethodDescriptor: The descriptor for the requested method.

    Raises:
      KeyError: if the method cannot be found in the service.
    """
    return self.methods_by_name[name]

  def CopyToProto(self, proto):
    """Copies this to a descriptor_pb2.ServiceDescriptorProto.

    Args:
      proto (descriptor_pb2.ServiceDescriptorProto): An empty descriptor proto.
    """
    # This function is overridden to give a better doc comment.
    super(ServiceDescriptor, self).CopyToProto(proto)


class MethodDescriptor(DescriptorBase):

  """Descriptor for a method in a service.

  Attributes:
    name (str): Name of the method within the service.
    full_name (str): Full name of method.
    index (int): 0-indexed index of the method inside the service.
    containing_service (ServiceDescriptor): The service that contains this
      method.
    input_type (Descriptor): The descriptor of the message that this method
      accepts.
    output_type (Descriptor): The descriptor of the message that this method
      returns.
    client_streaming (bool): Whether this method uses client streaming.
    server_streaming (bool): Whether this method uses server streaming.
    options (descriptor_pb2.MethodOptions or None): Method options message, or
      None to use default method options.
  """

  if _USE_C_DESCRIPTORS:
    _C_DESCRIPTOR_CLASS = _message.MethodDescriptor

    def __new__(cls,
                name,
                full_name,
                index,
                containing_service,
                input_type,
                output_type,
                client_streaming=False,
                server_streaming=False,
                options=None,
                serialized_options=None,
                create_key=None):
      _message.Message._CheckCalledFromGeneratedFile()  # pylint: disable=protected-access
      return _message.default_pool.FindMethodByName(full_name)

  def __init__(self,
               name,
               full_name,
               index,
               containing_service,
               input_type,
               output_type,
               client_streaming=False,
               server_streaming=False,
               options=None,
               serialized_options=None,
               create_key=None):
    """The arguments are as described in the description of MethodDescriptor
    attributes above.

    Note that containing_service may be None, and may be set later if necessary.
    """
    if create_key is not _internal_create_key:
      _Deprecated('MethodDescriptor')

    super(MethodDescriptor, self).__init__(
        containing_service.file if containing_service else None,
        options,
        serialized_options,
        'MethodOptions',
    )
    self.name = name
    self.full_name = full_name
    self.index = index
    self.containing_service = containing_service
    self.input_type = input_type
    self.output_type = output_type
    self.client_streaming = client_streaming
    self.server_streaming = server_streaming

  @property
  def _parent(self):
    return self.containing_service

  def CopyToProto(self, proto):
    """Copies this to a descriptor_pb2.MethodDescriptorProto.

    Args:
      proto (descriptor_pb2.MethodDescriptorProto): An empty descriptor proto.

    Raises:
      Error: If self couldn't be serialized, due to too few constructor
        arguments.
    """
    if self.containing_service is not None:
      from google.protobuf import descriptor_pb2
      service_proto = descriptor_pb2.ServiceDescriptorProto()
      self.containing_service.CopyToProto(service_proto)
      proto.CopyFrom(service_proto.method[self.index])
    else:
      raise Error('Descriptor does not contain a service.')


class FileDescriptor(DescriptorBase):
  """Descriptor for a file. Mimics the descriptor_pb2.FileDescriptorProto.

  Note that :attr:`enum_types_by_name`, :attr:`extensions_by_name`, and
  :attr:`dependencies` fields are only set by the
  :py:mod:`google.protobuf.message_factory` module, and not by the generated
  proto code.

  Attributes:
    name (str): Name of file, relative to root of source tree.
    package (str): Name of the package
    edition (Edition): Enum value indicating edition of the file
    serialized_pb (bytes): Byte string of serialized
      :class:`descriptor_pb2.FileDescriptorProto`.
    dependencies (list[FileDescriptor]): List of other :class:`FileDescriptor`
      objects this :class:`FileDescriptor` depends on.
    public_dependencies (list[FileDescriptor]): A subset of
      :attr:`dependencies`, which were declared as "public".
    message_types_by_name (dict(str, Descriptor)): Mapping from message names to
      their :class:`Descriptor`.
    enum_types_by_name (dict(str, EnumDescriptor)): Mapping from enum names to
      their :class:`EnumDescriptor`.
    extensions_by_name (dict(str, FieldDescriptor)): Mapping from extension
      names declared at file scope to their :class:`FieldDescriptor`.
    services_by_name (dict(str, ServiceDescriptor)): Mapping from services'
      names to their :class:`ServiceDescriptor`.
    pool (DescriptorPool): The pool this descriptor belongs to.  When not passed
      to the constructor, the global default pool is used.
  """

  if _USE_C_DESCRIPTORS:
    _C_DESCRIPTOR_CLASS = _message.FileDescriptor

    def __new__(
        cls,
        name,
        package,
        options=None,
        serialized_options=None,
        serialized_pb=None,
        dependencies=None,
        public_dependencies=None,
        syntax=None,
        edition=None,
        pool=None,
        create_key=None,
    ):
      # FileDescriptor() is called from various places, not only from generated
      # files, to register dynamic proto files and messages.
      # pylint: disable=g-explicit-bool-comparison
      if serialized_pb:
        return _message.default_pool.AddSerializedFile(serialized_pb)
      else:
        return super(FileDescriptor, cls).__new__(cls)

  def __init__(
      self,
      name,
      package,
      options=None,
      serialized_options=None,
      serialized_pb=None,
      dependencies=None,
      public_dependencies=None,
      syntax=None,
      edition=None,
      pool=None,
      create_key=None,
  ):
    """Constructor."""
    if create_key is not _internal_create_key:
      _Deprecated('FileDescriptor')

    super(FileDescriptor, self).__init__(
        self, options, serialized_options, 'FileOptions'
    )

    if edition and edition != 'EDITION_UNKNOWN':
      self._edition = edition
    elif syntax == 'proto3':
      self._edition = 'EDITION_PROTO3'
    else:
      self._edition = 'EDITION_PROTO2'

    if pool is None:
      from google.protobuf import descriptor_pool
      pool = descriptor_pool.Default()
    self.pool = pool
    self.message_types_by_name = {}
    self.name = name
    self.package = package
    self.serialized_pb = serialized_pb

    self.enum_types_by_name = {}
    self.extensions_by_name = {}
    self.services_by_name = {}
    self.dependencies = (dependencies or [])
    self.public_dependencies = (public_dependencies or [])

  def CopyToProto(self, proto):
    """Copies this to a descriptor_pb2.FileDescriptorProto.

    Args:
      proto: An empty descriptor_pb2.FileDescriptorProto.
    """
    proto.ParseFromString(self.serialized_pb)

  @property
  def _parent(self):
    return None


def _ParseOptions(message, string):
  """Parses serialized options.

  This helper function is used to parse serialized options in generated
  proto2 files. It must not be used outside proto2.
  """
  message.ParseFromString(string)
  return message


def _ToCamelCase(name):
  """Converts name to camel-case and returns it."""
  capitalize_next = False
  result = []

  for c in name:
    if c == '_':
      if result:
        capitalize_next = True
    elif capitalize_next:
      result.append(c.upper())
      capitalize_next = False
    else:
      result += c

  # Lower-case the first letter.
  if result and result[0].isupper():
    result[0] = result[0].lower()
  return ''.join(result)


def _OptionsOrNone(descriptor_proto):
  """Returns the value of the field `options`, or None if it is not set."""
  if descriptor_proto.HasField('options'):
    return descriptor_proto.options
  else:
    return None


def _ToJsonName(name):
  """Converts name to Json name and returns it."""
  capitalize_next = False
  result = []

  for c in name:
    if c == '_':
      capitalize_next = True
    elif capitalize_next:
      result.append(c.upper())
      capitalize_next = False
    else:
      result += c

  return ''.join(result)


def MakeDescriptor(
    desc_proto,
    package='',
    build_file_if_cpp=True,
    syntax=None,
    edition=None,
    file_desc=None,
):
  """Make a protobuf Descriptor given a DescriptorProto protobuf.

  Handles nested descriptors. Note that this is limited to the scope of defining
  a message inside of another message. Composite fields can currently only be
  resolved if the message is defined in the same scope as the field.

  Args:
    desc_proto: The descriptor_pb2.DescriptorProto protobuf message.
    package: Optional package name for the new message Descriptor (string).
    build_file_if_cpp: Update the C++ descriptor pool if api matches. Set to
      False on recursion, so no duplicates are created.
    syntax: The syntax/semantics that should be used.  Set to "proto3" to get
      proto3 field presence semantics.
    edition: The edition that should be used if syntax is "edition".
    file_desc: A FileDescriptor to place this descriptor into.

  Returns:
    A Descriptor for protobuf messages.
  """
  # pylint: disable=g-import-not-at-top
  from google.protobuf import descriptor_pb2

  # Generate a random name for this proto file to prevent conflicts with any
  # imported ones. We need to specify a file name so the descriptor pool
  # accepts our FileDescriptorProto, but it is not important what that file
  # name is actually set to.
  proto_name = binascii.hexlify(os.urandom(16)).decode('ascii')

  if package:
    file_name = os.path.join(package.replace('.', '/'), proto_name + '.proto')
  else:
    file_name = proto_name + '.proto'

  if api_implementation.Type() != 'python' and build_file_if_cpp:
    # The C++ implementation requires all descriptors to be backed by the same
    # definition in the C++ descriptor pool. To do this, we build a
    # FileDescriptorProto with the same definition as this descriptor and build
    # it into the pool.
    file_descriptor_proto = descriptor_pb2.FileDescriptorProto()
    file_descriptor_proto.message_type.add().MergeFrom(desc_proto)

    if package:
      file_descriptor_proto.package = package
    file_descriptor_proto.name = file_name

    _message.default_pool.Add(file_descriptor_proto)
    result = _message.default_pool.FindFileByName(file_descriptor_proto.name)

    if _USE_C_DESCRIPTORS:
      return result.message_types_by_name[desc_proto.name]

  if file_desc is None:
    file_desc = FileDescriptor(
        pool=None,
        name=file_name,
        package=package,
        syntax=syntax,
        edition=edition,
        options=None,
        serialized_pb='',
        dependencies=[],
        public_dependencies=[],
        create_key=_internal_create_key,
    )
  full_message_name = [desc_proto.name]
  if package: full_message_name.insert(0, package)

  # Create Descriptors for enum types
  enum_types = {}
  for enum_proto in desc_proto.enum_type:
    full_name = '.'.join(full_message_name + [enum_proto.name])
    enum_desc = EnumDescriptor(
        enum_proto.name,
        full_name,
        None,
        [
            EnumValueDescriptor(
                enum_val.name,
                ii,
                enum_val.number,
                create_key=_internal_create_key,
            )
            for ii, enum_val in enumerate(enum_proto.value)
        ],
        file=file_desc,
        create_key=_internal_create_key,
    )
    enum_types[full_name] = enum_desc

  # Create Descriptors for nested types
  nested_types = {}
  for nested_proto in desc_proto.nested_type:
    full_name = '.'.join(full_message_name + [nested_proto.name])
    # Nested types are just those defined inside of the message, not all types
    # used by fields in the message, so no loops are possible here.
    nested_desc = MakeDescriptor(
        nested_proto,
        package='.'.join(full_message_name),
        build_file_if_cpp=False,
        syntax=syntax,
        edition=edition,
        file_desc=file_desc,
    )
    nested_types[full_name] = nested_desc

  fields = []
  for field_proto in desc_proto.field:
    full_name = '.'.join(full_message_name + [field_proto.name])
    enum_desc = None
    nested_desc = None
    if field_proto.json_name:
      json_name = field_proto.json_name
    else:
      json_name = None
    if field_proto.HasField('type_name'):
      type_name = field_proto.type_name
      full_type_name = '.'.join(full_message_name +
                                [type_name[type_name.rfind('.')+1:]])
      if full_type_name in nested_types:
        nested_desc = nested_types[full_type_name]
      elif full_type_name in enum_types:
        enum_desc = enum_types[full_type_name]
      # Else type_name references a non-local type, which isn't implemented
    field = FieldDescriptor(
        field_proto.name,
        full_name,
        field_proto.number - 1,
        field_proto.number,
        field_proto.type,
        FieldDescriptor.ProtoTypeToCppProtoType(field_proto.type),
        field_proto.label,
        None,
        nested_desc,
        enum_desc,
        None,
        False,
        None,
        options=_OptionsOrNone(field_proto),
        has_default_value=False,
        json_name=json_name,
        file=file_desc,
        create_key=_internal_create_key,
    )
    fields.append(field)

  desc_name = '.'.join(full_message_name)
  return Descriptor(
      desc_proto.name,
      desc_name,
      None,
      None,
      fields,
      list(nested_types.values()),
      list(enum_types.values()),
      [],
      options=_OptionsOrNone(desc_proto),
      file=file_desc,
      create_key=_internal_create_key,
  )
