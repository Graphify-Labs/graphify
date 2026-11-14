"""#2810: PHP methods of one type that differ only by `_` stay separate nodes."""
from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    for name, src in files.items():
        (tmp_path / name).write_text(src, encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return extract([tmp_path / n for n in files], cache_root=tmp_path, root=tmp_path,
                       parallel=False)


def _members(r: dict) -> dict[str, str]:
    return {n["label"]: n["id"] for n in r["nodes"] if n["label"].startswith(".")}


def _calls(r: dict) -> set[tuple[str | None, str | None]]:
    label = {n["id"]: n["label"] for n in r["nodes"]}
    return {(label.get(e["source"]), label.get(e["target"]))
            for e in r["edges"] if e["relation"] == "calls"}


_CLASS_B = (
    "<?php\n"
    "class B {\n"
    "    private function _x() { return 1; }\n"
    "    public function x() { return $this->_x(); }\n"
    "    public function y() { return $this->x(); }\n"
    "}\n"
)


def test_both_methods_are_nodes_with_distinct_ids(tmp_path):
    r = _extract(tmp_path, {"b.php": _CLASS_B})
    m = _members(r)
    assert {"._x()", ".x()", ".y()"} <= set(m)
    assert m["._x()"] != m[".x()"]
    owned = {e["target"] for e in r["edges"] if e["relation"] == "method" and e["source"] == "b_b"}
    assert {m["._x()"], m[".x()"], m[".y()"]} <= owned


def test_public_method_keeps_the_plain_id_and_private_one_is_salted(tmp_path):
    m = _members(_extract(tmp_path, {"b.php": _CLASS_B}))
    assert m[".x()"] == "b_b_x"
    assert m["._x()"].startswith("b_b_x_") and m["._x()"] != "b_b_x"


def test_calls_bind_to_the_right_method_and_no_self_loop(tmp_path):
    r = _extract(tmp_path, {"b.php": _CLASS_B})
    calls = _calls(r)
    assert (".x()", "._x()") in calls
    assert (".y()", ".x()") in calls
    assert not any(e["source"] == e["target"] for e in r["edges"] if e["relation"] == "calls")


@pytest.mark.parametrize("use_src", [
    "<?php\nfunction outside() { $b = new B(); return $b->x(); }\n",
    "<?php\nfunction outside(B $b) { return $b->x(); }\n",
])
def test_external_call_binds_to_the_public_method(tmp_path, use_src):
    r = _extract(tmp_path, {"b.php": _CLASS_B, "use.php": use_src})
    calls = _calls(r)
    assert ("outside()", ".x()") in calls
    assert ("outside()", "._x()") not in calls


def test_order_does_not_matter(tmp_path):
    (tmp_path / "1").mkdir()
    (tmp_path / "2").mkdir()
    a = _members(_extract(tmp_path / "1", {"a.php": (
        "<?php\nclass A { private function _x() {} public function x() {} }\n")}))
    b = _members(_extract(tmp_path / "2", {"a.php": (
        "<?php\nclass A { public function x() {} private function _x() {} }\n")}))
    assert a == b
    assert a[".x()"] == "a_a_x"


def test_non_colliding_method_ids_unchanged(tmp_path):
    m = _members(_extract(tmp_path, {"c.php": (
        "<?php\nclass C {\n"
        "    public function run() {}\n"
        "    private function _helper() {}\n"
        "    public function __construct() {}\n"
        "    public static function make() {}\n"
        "}\n")}))
    assert m == {".run()": "c_c_run", "._helper()": "c_c_helper",
                 ".__construct()": "c_c_construct", ".make()": "c_c_make"}


def test_trait_with_the_same_pattern(tmp_path):
    r = _extract(tmp_path, {"t.php": (
        "<?php\ntrait T {\n"
        "    protected function _x() { return 1; }\n"
        "    public function x() { return $this->_x(); }\n"
        "    public function y() { return $this->x(); }\n"
        "}\n")})
    m = _members(r)
    assert m[".x()"] == "t_t_x" and m["._x()"] != m[".x()"]
    calls = _calls(r)
    assert (".x()", "._x()") in calls
    assert (".y()", ".x()") in calls


@pytest.mark.parametrize("src", [
    "<?php\ninterface I { public function _x(); public function x(); }\n",
    "<?php\nenum I { case A; private function _x() {} public function x() {} }\n",
    "<?php\nabstract class I { abstract protected function _x(); public function x() {} }\n",
])
def test_interface_enum_and_abstract_bodies(tmp_path, src):
    m = _members(_extract(tmp_path, {"i.php": src}))
    assert m[".x()"] == "i_i_x"
    assert m["._x()"].startswith("i_i_x_")


def test_method_names_are_case_insensitive(tmp_path):
    # PHP method names are case-insensitive: `Run()` is still the one public
    # name next to `_run()`, so it keeps the plain id and the calls split.
    r = _extract(tmp_path, {"k.php": (
        "<?php\nclass K {\n"
        "    private function _run() { return 1; }\n"
        "    public function Run() { return $this->_run(); }\n"
        "    public function go() { return $this->Run(); }\n"
        "}\n")})
    m = _members(r)
    assert m[".Run()"] == "k_k_run" and m["._run()"] != "k_k_run"
    calls = _calls(r)
    assert (".Run()", "._run()") in calls
    assert (".go()", ".Run()") in calls


def test_salt_does_not_depend_on_case(tmp_path):
    (tmp_path / "1").mkdir()
    (tmp_path / "2").mkdir()
    a = _members(_extract(tmp_path / "1", {"a.php": (
        "<?php\nclass A { private function _x() {} public function x() {} }\n")}))
    b = _members(_extract(tmp_path / "2", {"a.php": (
        "<?php\nclass A { private function _X() {} public function X() {} }\n")}))
    assert a["._x()"] == b["._X()"] and a[".x()"] == b[".X()"]
