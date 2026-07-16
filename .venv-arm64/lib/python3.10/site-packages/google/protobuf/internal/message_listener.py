# Protocol Buffers - Google's data interchange format
# Copyright 2008 Google Inc.  All rights reserved.
#
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file or at
# https://developers.google.com/open-source/licenses/bsd

"""Defines a listener interface for observing certain
state transitions on Message objects.

Also defines a null implementation of this interface.
"""

__author__ = 'robinson@google.com (Will Robinson)'


class MessageListener(object):

  """Listens for modifications made to a message.  Meant to be registered via
  Message._SetListener().

  Attributes:
    dirty:  If True, then calling Modified() would be a no-op.  This can be
            used to avoid these calls entirely in the common case.
  """

  def Modified(self):
    """Called every time the message is modified in such a way that the parent
    message may need to be updated.  This currently means either:
    (a) The message was modified for the first time, so the parent message
        should henceforth mark the message as present.
    (b) The message's cached byte size became dirty -- i.e. the message was
        modified for the first time after a previous call to ByteSize().
        Therefore the parent should also mark its byte size as dirty.
    Note that (a) implies (b), since new objects start out with a client cached
    size (zero).  However, we document (a) explicitly because it is important.

    Modified() will *only* be called in response to one of these two events --
    not every time the sub-message is modified.

    Note that if the listener's |dirty| attribute is true, then calling
    Modified at the moment would be a no-op, so it can be skipped.  Performance-
    sensitive callers should check this attribute directly before calling since
    it will be true most of the time.
    """

    raise NotImplementedError


class NullMessageListener(object):

  """No-op MessageListener implementation."""

  def Modified(self):
    pass
