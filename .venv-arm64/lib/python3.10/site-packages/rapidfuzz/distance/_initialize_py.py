# SPDX-License-Identifier: MIT
# Copyright (C) 2022 Max Bachmann
from __future__ import annotations


def _list_to_editops(
    ops,
    src_len,
    dest_len,
):
    if not ops:
        return []

    if len(ops[0]) == 5:
        return Opcodes(ops, src_len, dest_len).as_editops()._editops

    blocks = []
    for op in ops:
        edit_type, src_pos, dest_pos = op

        if src_pos > src_len or dest_pos > dest_len:
            msg = "List of edit operations invalid"
            raise ValueError(msg)

        if src_pos == src_len and edit_type != "insert":
            msg = "List of edit operations invalid"
            raise ValueError(msg)
        if dest_pos == dest_len and edit_type != "delete":
            msg = "List of edit operations invalid"
            raise ValueError(msg)

        # keep operations are not relevant in editops
        if edit_type == "equal":
            continue

        blocks.append(Editop(edit_type, src_pos, dest_pos))

    # validate order of editops
    for i in range(len(blocks) - 1):
        if blocks[i + 1].src_pos < blocks[i].src_pos or blocks[i + 1].dest_pos < blocks[i].dest_pos:
            msg = "List of edit operations out of order"
            raise ValueError(msg)
        if blocks[i + 1].src_pos == blocks[i].src_pos and blocks[i + 1].dest_pos == blocks[i].dest_pos:
            msg = "Duplicated edit operation"
            raise ValueError(msg)

    return blocks


def _list_to_opcodes(
    ops,
    src_len,
    dest_len,
):
    if not ops or len(ops[0]) == 3:
        return Editops(ops, src_len, dest_len).as_opcodes()._opcodes

    blocks = []
    for op in ops:
        edit_type, src_start, src_end, dest_start, dest_end = op

        if src_end > src_len or dest_end > dest_len:
            msg = "List of edit operations invalid"
            raise ValueError(msg)
        if src_end < src_start or dest_end < dest_start:
            msg = "List of edit operations invalid"
            raise ValueError(msg)

        if edit_type in {"equal", "replace"} and (src_end - src_start != dest_end - dest_start or src_start == src_end):
            msg = "List of edit operations invalid"
            raise ValueError(msg)
        if edit_type == "insert" and (src_start != src_end or dest_start == dest_end):
            msg = "List of edit operations invalid"
            raise ValueError(msg)
        if edit_type == "delete" and (src_start == src_end or dest_start != dest_end):
            msg = "List of edit operations invalid"
            raise ValueError(msg)

        # merge similar adjacent blocks
        if blocks and (
            blocks[-1].tag == edit_type and blocks[-1].src_end == src_start and blocks[-1].dest_end == dest_start
        ):
            blocks[-1].src_end = src_end
            blocks[-1].dest_end = dest_end
            continue

        blocks.append(Opcode(edit_type, src_start, src_end, dest_start, dest_end))

    # check if edit operations span the complete string
    if blocks[0].src_start != 0 or blocks[0].dest_start != 0:
        msg = "List of edit operations does not start at position 0"
        raise ValueError(msg)
    if blocks[-1].src_end != src_len or blocks[-1].dest_end != dest_len:
        msg = "List of edit operations does not end at the string ends"
        raise ValueError(msg)
    for i in range(len(blocks) - 1):
        if blocks[i + 1].src_start != blocks[i].src_end or blocks[i + 1].dest_start != blocks[i].dest_end:
            msg = "List of edit operations is not continuous"
            raise ValueError(msg)

    return blocks


class MatchingBlock:
    """
    Triple describing matching subsequences
    """

    def __init__(self, a, b, size):
        self.a = a
        self.b = b
        self.size = size

    def __len__(self):
        return 3

    def __eq__(self, other):
        try:
            if len(other) != 3:
                return False

            return bool(other[0] == self.a and other[1] == self.b and other[2] == self.size)
        except TypeError:
            return False

    def __getitem__(self, i):
        if i in {0, -3}:
            return self.a
        if i in {1, -2}:
            return self.b
        if i in {2, -1}:
            return self.size

        msg = "MatchingBlock index out of range"
        raise IndexError(msg)

    def __iter__(self):
        for i in range(3):
            yield self[i]

    def __repr__(self):
        return f"MatchingBlock(a={self.a}, b={self.b}, size={self.size})"


class Editop:
    """
    Tuple like object describing an edit operation.
    It is in the form (tag, src_pos, dest_pos)

    The tags are strings, with these meanings:

    +-----------+---------------------------------------------------+
    | tag       | explanation                                       |
    +===========+===================================================+
    | 'replace' | src[src_pos] should be replaced by dest[dest_pos] |
    +-----------+---------------------------------------------------+
    | 'delete'  | src[src_pos] should be deleted                    |
    +-----------+---------------------------------------------------+
    | 'insert'  | dest[dest_pos] should be inserted at src[src_pos] |
    +-----------+---------------------------------------------------+
    """

    def __init__(self, tag, src_pos, dest_pos):
        self.tag = tag
        self.src_pos = src_pos
        self.dest_pos = dest_pos

    def __len__(self):
        return 3

    def __eq__(self, other):
        try:
            if len(other) != 3:
                return False

            return bool(other[0] == self.tag and other[1] == self.src_pos and other[2] == self.dest_pos)
        except TypeError:
            return False

    def __getitem__(self, i):
        if i in {0, -3}:
            return self.tag
        if i in {1, -2}:
            return self.src_pos
        if i in {2, -1}:
            return self.dest_pos

        msg = "Editop index out of range"
        raise IndexError(msg)

    def __iter__(self):
        for i in range(3):
            yield self[i]

    def __repr__(self):
        return f"Editop(tag={self.tag!r}, src_pos={self.src_pos}, dest_pos={self.dest_pos})"


class Editops:
    """
    List like object of Editops describing how to turn s1 into s2.
    """

    def __init__(
        self,
        editops=None,
        src_len=0,
        dest_len=0,
    ):
        self._src_len = src_len
        self._dest_len = dest_len
        self._editops = _list_to_editops(editops, src_len, dest_len)

    @classmethod
    def from_opcodes(cls, opcodes):
        """
        Create Editops from Opcodes

        Parameters
        ----------
        opcodes : Opcodes
            opcodes to convert to editops

        Returns
        -------
        editops : Editops
            Opcodes converted to Editops
        """
        return opcodes.as_editops()

    def as_opcodes(self):
        """
        Convert to Opcodes

        Returns
        -------
        opcodes : Opcodes
            Editops converted to Opcodes
        """
        x = Opcodes.__new__(Opcodes)
        x._src_len = self._src_len
        x._dest_len = self._dest_len
        blocks = []
        src_pos = 0
        dest_pos = 0
        i = 0
        while i < len(self._editops):
            if src_pos < self._editops[i].src_pos or dest_pos < self._editops[i].dest_pos:
                blocks.append(
                    Opcode(
                        "equal",
                        src_pos,
                        self._editops[i].src_pos,
                        dest_pos,
                        self._editops[i].dest_pos,
                    )
                )
                src_pos = self._editops[i].src_pos
                dest_pos = self._editops[i].dest_pos

            src_begin = src_pos
            dest_begin = dest_pos
            tag = self._editops[i].tag
            while (
                i < len(self._editops)
                and self._editops[i].tag == tag
                and src_pos == self._editops[i].src_pos
                and dest_pos == self._editops[i].dest_pos
            ):
                if tag == "replace":
                    src_pos += 1
                    dest_pos += 1
                elif tag == "insert":
                    dest_pos += 1
                elif tag == "delete":
                    src_pos += 1

                i += 1

            blocks.append(Opcode(tag, src_begin, src_pos, dest_begin, dest_pos))

        if src_pos < self.src_len or dest_pos < self.dest_len:
            blocks.append(Opcode("equal", src_pos, self.src_len, dest_pos, self.dest_len))

        x._opcodes = blocks
        return x

    def as_matching_blocks(self):
        """
        Convert to matching blocks

        Returns
        -------
        matching blocks : list[MatchingBlock]
            Editops converted to matching blocks
        """
        blocks = []
        src_pos = 0
        dest_pos = 0
        for op in self:
            if src_pos < op.src_pos or dest_pos < op.dest_pos:
                length = min(op.src_pos - src_pos, op.dest_pos - dest_pos)
                if length > 0:
                    blocks.append(MatchingBlock(src_pos, dest_pos, length))
                src_pos = op.src_pos
                dest_pos = op.dest_pos

            if op.tag == "replace":
                src_pos += 1
                dest_pos += 1
            elif op.tag == "delete":
                src_pos += 1
            elif op.tag == "insert":
                dest_pos += 1

        if src_pos < self.src_len or dest_pos < self.dest_len:
            length = min(self.src_len - src_pos, self.dest_len - dest_pos)
            if length > 0:
                blocks.append(MatchingBlock(src_pos, dest_pos, length))

        blocks.append(MatchingBlock(self.src_len, self.dest_len, 0))
        return blocks

    def as_list(self):
        """
        Convert Editops to a list of tuples.

        This is the equivalent of ``[x for x in editops]``
        """
        return [tuple(op) for op in self._editops]

    def copy(self):
        """
        performs copy of Editops
        """
        x = Editops.__new__(Editops)
        x._src_len = self._src_len
        x._dest_len = self._dest_len
        x._editops = self._editops[::]
        return x

    def inverse(self):
        """
        Invert Editops, so it describes how to transform the destination string to
        the source string.

        Returns
        -------
        editops : Editops
            inverted Editops

        Examples
        --------
        >>> from rapidfuzz.distance import Levenshtein
        >>> Levenshtein.editops('spam', 'park')
        [Editop(tag=delete, src_pos=0, dest_pos=0),
         Editop(tag=replace, src_pos=3, dest_pos=2),
         Editop(tag=insert, src_pos=4, dest_pos=3)]

        >>> Levenshtein.editops('spam', 'park').inverse()
        [Editop(tag=insert, src_pos=0, dest_pos=0),
         Editop(tag=replace, src_pos=2, dest_pos=3),
         Editop(tag=delete, src_pos=3, dest_pos=4)]
        """
        blocks = []
        for op in self:
            tag = op.tag
            if tag == "delete":
                tag = "insert"
            elif tag == "insert":
                tag = "delete"

            blocks.append(Editop(tag, op.dest_pos, op.src_pos))

        x = Editops.__new__(Editops)
        x._src_len = self.dest_len
        x._dest_len = self.src_len
        x._editops = blocks
        return x

    def remove_subsequence(self, subsequence):
        """
        remove a subsequence

        Parameters
        ----------
        subsequence : Editops
            subsequence to remove (has to be a subset of editops)

        Returns
        -------
        sequence : Editops
            a copy of the editops without the subsequence
        """
        result = Editops.__new__(Editops)
        result._src_len = self._src_len
        result._dest_len = self._dest_len

        if len(subsequence) > len(self):
            msg = "subsequence is not a subsequence"
            raise ValueError(msg)

        result._editops = [None] * (len(self) - len(subsequence))

        # offset to correct removed edit operation
        offset = 0
        op_pos = 0
        result_pos = 0

        for sop in subsequence:
            while op_pos != len(self) and sop != self._editops[op_pos]:
                result[result_pos] = self._editops[op_pos]
                result[result_pos].src_pos += offset
                result_pos += 1
                op_pos += 1

            # element of subsequence not part of the sequence
            if op_pos == len(self):
                msg = "subsequence is not a subsequence"
                raise ValueError(msg)

            if sop.tag == "insert":
                offset += 1
            elif sop.tag == "delete":
                offset -= 1

            op_pos += 1

        # add remaining elements
        while op_pos != len(self):
            result[result_pos] = self._editops[op_pos]
            result[result_pos].src_pos += offset
            result_pos += 1
            op_pos += 1

        return result

    def apply(self, source_string, destination_string):
        """
        apply editops to source_string

        Parameters
        ----------
        source_string : str | bytes
            string to apply editops to
        destination_string : str | bytes
            string to use for replacements / insertions into source_string

        Returns
        -------
        mod_string : str
            modified source_string

        """
        res_str = ""
        src_pos = 0

        for op in self._editops:
            # matches between last and current editop
            while src_pos < op.src_pos:
                res_str += source_string[src_pos]
                src_pos += 1

            if op.tag == "replace":
                res_str += destination_string[op.dest_pos]
                src_pos += 1
            elif op.tag == "insert":
                res_str += destination_string[op.dest_pos]
            elif op.tag == "delete":
                src_pos += 1

        # matches after the last editop
        while src_pos < len(source_string):
            res_str += source_string[src_pos]
            src_pos += 1

        return res_str

    @property
    def src_len(self):
        return self._src_len

    @src_len.setter
    def src_len(self, value):
        self._src_len = value

    @property
    def dest_len(self):
        return self._dest_len

    @dest_len.setter
    def dest_len(self, value):
        self._dest_len = value

    def __eq__(self, other):
        if not isinstance(other, Editops):
            return False

        return self.dest_len == other.dest_len and self.src_len == other.src_len and self._editops == other._editops

    def __len__(self):
        return len(self._editops)

    def __delitem__(self, key):
        del self._editops[key]

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._editops[key]

        start, stop, step = key.indices(len(self._editops))
        if step < 0:
            msg = "step sizes below 0 lead to an invalid order of editops"
            raise ValueError(msg)

        x = Editops.__new__(Editops)
        x._src_len = self._src_len
        x._dest_len = self._dest_len
        x._editops = self._editops[start:stop:step]
        return x

    def __iter__(self):
        yield from self._editops

    def __repr__(self):
        return (
            "Editops([" + ", ".join(repr(op) for op in self) + f"], src_len={self.src_len}, dest_len={self.dest_len})"
        )


class Opcode:
    """
    Tuple like object describing an edit operation.
    It is in the form (tag, src_start, src_end, dest_start, dest_end)

    The tags are strings, with these meanings:

    +-----------+-----------------------------------------------------+
    | tag       | explanation                                         |
    +===========+=====================================================+
    | 'replace' | src[src_start:src_end] should be                    |
    |           | replaced by dest[dest_start:dest_end]               |
    +-----------+-----------------------------------------------------+
    | 'delete'  | src[src_start:src_end] should be deleted.           |
    |           | Note that dest_start==dest_end in this case.        |
    +-----------+-----------------------------------------------------+
    | 'insert'  | dest[dest_start:dest_end] should be inserted        |
    |           | at src[src_start:src_start].                        |
    |           | Note that src_start==src_end in this case.          |
    +-----------+-----------------------------------------------------+
    | 'equal'   | src[src_start:src_end] == dest[dest_start:dest_end] |
    +-----------+-----------------------------------------------------+

    Note
    ----
    Opcode is compatible with the tuples returned by difflib's SequenceMatcher to make them
    interoperable
    """

    def __init__(self, tag, src_start, src_end, dest_start, dest_end):
        self.tag = tag
        self.src_start = src_start
        self.src_end = src_end
        self.dest_start = dest_start
        self.dest_end = dest_end

    def __len__(self):
        return 5

    def __eq__(self, other):
        try:
            if len(other) != 5:
                return False

            return bool(
                other[0] == self.tag
                and other[1] == self.src_start
                and other[2] == self.src_end
                and other[3] == self.dest_start
                and other[4] == self.dest_end
            )
        except TypeError:
            return False

    def __getitem__(self, i):
        if i in {0, -5}:
            return self.tag
        if i in {1, -4}:
            return self.src_start
        if i in {2, -3}:
            return self.src_end
        if i in {3, -2}:
            return self.dest_start
        if i in {4, -1}:
            return self.dest_end

        msg = "Opcode index out of range"
        raise IndexError(msg)

    def __iter__(self):
        for i in range(5):
            yield self[i]

    def __repr__(self):
        return (
            f"Opcode(tag={self.tag!r}, src_start={self.src_start}, src_end={self.src_end}, "
            f"dest_start={self.dest_start}, dest_end={self.dest_end})"
        )


class Opcodes:
    """
    List like object of Opcodes describing how to turn s1 into s2.
    The first Opcode has src_start == dest_start == 0, and remaining tuples
    have src_start == the src_end from the tuple preceding it,
    and likewise for dest_start == the previous dest_end.
    """

    def __init__(
        self,
        opcodes=None,
        src_len=0,
        dest_len=0,
    ):
        self._src_len = src_len
        self._dest_len = dest_len
        self._opcodes = _list_to_opcodes(opcodes, src_len, dest_len)

    @classmethod
    def from_editops(cls, editops):
        """
        Create Opcodes from Editops

        Parameters
        ----------
        editops : Editops
            editops to convert to opcodes

        Returns
        -------
        opcodes : Opcodes
            Editops converted to Opcodes
        """
        return editops.as_opcodes()

    def as_editops(self):
        """
        Convert Opcodes to Editops

        Returns
        -------
        editops : Editops
            Opcodes converted to Editops
        """
        x = Editops.__new__(Editops)
        x._src_len = self._src_len
        x._dest_len = self._dest_len
        blocks = []
        for op in self:
            if op.tag == "replace":
                for j in range(op.src_end - op.src_start):
                    blocks.append(Editop("replace", op.src_start + j, op.dest_start + j))
            elif op.tag == "insert":
                for j in range(op.dest_end - op.dest_start):
                    blocks.append(Editop("insert", op.src_start, op.dest_start + j))
            elif op.tag == "delete":
                for j in range(op.src_end - op.src_start):
                    blocks.append(Editop("delete", op.src_start + j, op.dest_start))

        x._editops = blocks
        return x

    def as_matching_blocks(self):
        """
        Convert to matching blocks

        Returns
        -------
        matching blocks : list[MatchingBlock]
            Opcodes converted to matching blocks
        """
        blocks = []
        for op in self:
            if op.tag == "equal":
                length = min(op.src_end - op.src_start, op.dest_end - op.dest_start)
                if length > 0:
                    blocks.append(MatchingBlock(op.src_start, op.dest_start, length))

        blocks.append(MatchingBlock(self.src_len, self.dest_len, 0))
        return blocks

    def as_list(self):
        """
        Convert Opcodes to a list of tuples, which is compatible
        with the opcodes of difflibs SequenceMatcher.

        This is the equivalent of ``[x for x in opcodes]``
        """
        return [tuple(op) for op in self._opcodes]

    def copy(self):
        """
        performs copy of Opcodes
        """
        x = Opcodes.__new__(Opcodes)
        x._src_len = self._src_len
        x._dest_len = self._dest_len
        x._opcodes = self._opcodes[::]
        return x

    def inverse(self):
        """
        Invert Opcodes, so it describes how to transform the destination string to
        the source string.

        Returns
        -------
        opcodes : Opcodes
            inverted Opcodes

        Examples
        --------
        >>> from rapidfuzz.distance import Levenshtein
        >>> Levenshtein.opcodes('spam', 'park')
        [Opcode(tag=delete, src_start=0, src_end=1, dest_start=0, dest_end=0),
         Opcode(tag=equal, src_start=1, src_end=3, dest_start=0, dest_end=2),
         Opcode(tag=replace, src_start=3, src_end=4, dest_start=2, dest_end=3),
         Opcode(tag=insert, src_start=4, src_end=4, dest_start=3, dest_end=4)]

        >>> Levenshtein.opcodes('spam', 'park').inverse()
        [Opcode(tag=insert, src_start=0, src_end=0, dest_start=0, dest_end=1),
         Opcode(tag=equal, src_start=0, src_end=2, dest_start=1, dest_end=3),
         Opcode(tag=replace, src_start=2, src_end=3, dest_start=3, dest_end=4),
         Opcode(tag=delete, src_start=3, src_end=4, dest_start=4, dest_end=4)]
        """
        blocks = []
        for op in self:
            tag = op.tag
            if tag == "delete":
                tag = "insert"
            elif tag == "insert":
                tag = "delete"

            blocks.append(Opcode(tag, op.dest_start, op.dest_end, op.src_start, op.src_end))

        x = Opcodes.__new__(Opcodes)
        x._src_len = self.dest_len
        x._dest_len = self.src_len
        x._opcodes = blocks
        return x

    def apply(self, source_string, destination_string):
        """
        apply opcodes to source_string

        Parameters
        ----------
        source_string : str | bytes
            string to apply opcodes to
        destination_string : str | bytes
            string to use for replacements / insertions into source_string

        Returns
        -------
        mod_string : str
            modified source_string

        """
        res_str = ""

        for op in self._opcodes:
            if op.tag == "equal":
                res_str += source_string[op.src_start : op.src_end]
            elif op.tag in {"replace", "insert"}:
                res_str += destination_string[op.dest_start : op.dest_end]

        return res_str

    @property
    def src_len(self):
        return self._src_len

    @src_len.setter
    def src_len(self, value):
        self._src_len = value

    @property
    def dest_len(self):
        return self._dest_len

    @dest_len.setter
    def dest_len(self, value):
        self._dest_len = value

    def __eq__(self, other):
        if not isinstance(other, Opcodes):
            return False

        return self.dest_len == other.dest_len and self.src_len == other.src_len and self._opcodes == other._opcodes

    def __len__(self):
        return len(self._opcodes)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._opcodes[key]

        msg = "Expected index"
        raise TypeError(msg)

    def __iter__(self):
        yield from self._opcodes

    def __repr__(self):
        return (
            "Opcodes([" + ", ".join(repr(op) for op in self) + f"], src_len={self.src_len}, dest_len={self.dest_len})"
        )


class ScoreAlignment:
    """
    Tuple like object describing the position of the compared strings in
    src and dest.

    It indicates that the score has been calculated between
    src[src_start:src_end] and dest[dest_start:dest_end]
    """

    def __init__(
        self,
        score,
        src_start,
        src_end,
        dest_start,
        dest_end,
    ):
        self.score = score
        self.src_start = src_start
        self.src_end = src_end
        self.dest_start = dest_start
        self.dest_end = dest_end

    def __len__(self):
        return 5

    def __eq__(self, other):
        try:
            if len(other) != 5:
                return False

            return bool(
                other[0] == self.score
                and other[1] == self.src_start
                and other[2] == self.src_end
                and other[3] == self.dest_start
                and other[4] == self.dest_end
            )
        except TypeError:
            return False

    def __getitem__(self, i):
        if i in {0, -5}:
            return self.score
        if i in {1, -4}:
            return self.src_start
        if i in {2, -3}:
            return self.src_end
        if i in {3, -2}:
            return self.dest_start
        if i in {4, -1}:
            return self.dest_end

        msg = "Opcode index out of range"
        raise IndexError(msg)

    def __iter__(self):
        for i in range(5):
            yield self[i]

    def __repr__(self):
        return (
            f"ScoreAlignment(score={self.score}, src_start={self.src_start}, "
            f"src_end={self.src_end}, dest_start={self.dest_start}, dest_end={self.dest_end})"
        )
