"""Tests for files that do not end with a newline.

In C and C++, if the .h file does not end with a newline '\n' an error
is throwed even if the file is valid. In order to avoid this, a new line
char is added only if the original file does not end with it.

In this test we will make sure this works.
"""

from graphify.extract import extract, extract_c, extract_cpp

TEST_HEADER_1 = """\
#define A 8
#define AA 3"""

TEST_HEADER_2 = """\
#define A 8

int foo(int bar) { return bar; }

int foo2(void) { return 0; }

#define AA 1"""

TEST_HEADER_3 = """\
#pragma once

#define A 4"""


def write(path, text):
    path.write_bytes(text.encode("utf-8"))
    return path


def stderr_of(tmp_path, path, capsys):
    extract([path], root=tmp_path)
    return capsys.readouterr().err


def test_c_header_without_newline(tmp_path, capsys):
    path = write(tmp_path / "test_header.h", TEST_HEADER_1)
    assert "partially extracted" not in stderr_of(tmp_path, path, capsys)


def test_cpp_header_without_newline(tmp_path, capsys):
    path = write(tmp_path / "test_header.hpp", TEST_HEADER_3)
    assert "partially extracted" not in stderr_of(tmp_path, path, capsys)


def test_c_header_with_newline(tmp_path, capsys):
    path = write(tmp_path / "test_header.h", TEST_HEADER_1 + "\n")
    assert "partially extracted" not in stderr_of(tmp_path, path, capsys)


def test_no_parse_errors(tmp_path):
    assert extract_c(write(tmp_path / "test_header.h", TEST_HEADER_1)).get("parse_errors") is None
    assert extract_cpp(write(tmp_path / "test_header.hpp", TEST_HEADER_3)).get("parse_errors") is None


def test_functions_are_still_found(tmp_path):
    path = write(tmp_path / "test_header.h", TEST_HEADER_2)
    labels = [node["label"] for node in extract_c(path)["nodes"]]
    assert "foo()" in labels
    assert "foo2()" in labels


def test_empty_file(tmp_path):
    path = write(tmp_path / "test_header.c", "")
    assert extract_c(path).get("parse_errors") is None
