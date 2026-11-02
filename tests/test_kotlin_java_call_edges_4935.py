"""Kotlin and Java ``calls`` edges that were missing or wrong (#4935).

Three independent causes, one test group each:

* Overloads. Java gives every overload of a method the same node id, so the
  type carries two ``method`` edges to one target. The Kotlin member-call
  resolver counted list entries instead of distinct ids and read one node as an
  ambiguous match.
* ``init`` blocks. Kotlin's ``anonymous_initializer`` was never walked, so its
  calls had no source to attach to. Property initializers (#2565) already feed
  the same walker, so ``init`` follows them.
* Inherited external methods. A bare ``getString(1)`` in a class that extends
  an out-of-repo class bound to the only ``getString`` in the corpus, a method
  of an unrelated class that the caller cannot reach.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

LOGGER_JAVA = """\
package util;
public class Logger {
    public static int single(String t) { return 0; }
    public static int overloaded(String t) { return 0; }
    public static int overloaded(String t, String m) { return 0; }
}
"""
PREFS_JAVA = """\
package util;
public class Prefs { public String getString(String k) { return k; } }
"""
SETTINGS_KT = """\
package util
object Settings {
    fun get(k: String): String = k
    fun get(k: String, d: String): String = d
    fun fetchValue(k: String): String = k
}
"""


def _calls(tmp_path: Path, files: dict[str, str]) -> set[tuple[str, str]]:
    """``calls`` edges as ``("File:label", "File:label")`` pairs."""
    paths = []
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        paths.append(p)
    r = extract(paths, cache_root=tmp_path, parallel=False)
    where = {
        n["id"]: f'{Path(n.get("source_file", "")).stem}:{n["label"]}'
        for n in r["nodes"]
    }
    return {
        (where[e["source"]], where[e["target"]])
        for e in r["edges"]
        if e["relation"] == "calls" and e["source"] in where and e["target"] in where
    }


# ---- controls: behaviour that must not change --------------------------------

def test_kotlin_call_to_a_non_overloaded_java_method_resolves(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Logger.java": LOGGER_JAVA,
        "app/Caller.kt": "package app\nimport util.Logger\n"
                         "class Caller { fun go() { Logger.single(\"a\") } }\n",
    })
    assert ("Caller:.go()", "Logger:.single()") in edges


def test_a_property_initializer_call_still_resolves(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Logger.java": LOGGER_JAVA,
        "app/Holder.kt": "package app\nimport util.Logger\n"
                         "class Holder { val x = Logger.single(\"a\") }\n",
    })
    assert ("Holder:Holder", "Logger:.single()") in edges


def test_two_classes_with_the_same_name_stay_ambiguous(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "a/Dup.java": "package a;\npublic class Dup { public static void ping() {} }\n",
        "b/Dup.java": "package b;\npublic class Dup { public static void ping() {} }\n",
        "app/Caller.kt": "package app\nimport a.Dup\n"
                         "class Caller { fun go() { Dup.ping() } }\n",
    })
    assert not {e for e in edges if e[0].startswith("Caller")}


def test_inherited_in_repo_members_still_resolve(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/RepoBase.kt": "package util\nopen class RepoBase { fun baseHelper() {} }\n",
        "util/JavaBase.java": "package util;\npublic class JavaBase { public void baseJava() {} }\n",
        "app/KChild.kt": "package app\nimport util.RepoBase\n"
                         "class KChild : RepoBase() { fun t() = baseHelper() }\n",
        "app/JChild.java": "package app;\nimport util.JavaBase;\n"
                           "public class JChild extends JavaBase { public void t() { baseJava(); } }\n",
    })
    assert ("KChild:.t()", "RepoBase:.baseHelper()") in edges
    assert ("JChild:.t()", "JavaBase:.baseJava()") in edges


# ---- overloads ---------------------------------------------------------------

def test_kotlin_call_to_an_overloaded_java_method_resolves(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Logger.java": LOGGER_JAVA,
        "app/Caller.kt": "package app\nimport util.Logger\n"
                         "class Caller { fun go() { Logger.overloaded(\"a\") } }\n",
    })
    assert ("Caller:.go()", "Logger:.overloaded()") in edges


def test_kotlin_call_to_an_overloaded_kotlin_object_method_resolves(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Settings.kt": SETTINGS_KT,
        "app/Caller.kt": "package app\nimport util.Settings\n"
                         "class Caller { fun go() { Settings.get(\"a\") } }\n",
    })
    assert ("Caller:.go()", "Settings:.get()") in edges
