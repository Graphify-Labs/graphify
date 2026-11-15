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


# ---- init blocks -------------------------------------------------------------

def test_an_init_block_call_attaches_to_its_class(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Logger.java": LOGGER_JAVA,
        "app/Boot.kt": "package app\nimport util.Logger\n"
                       "class Boot { init { Logger.single(\"a\") } }\n",
    })
    assert ("Boot:Boot", "Logger:.single()") in edges


def test_an_init_block_call_to_an_overloaded_method_resolves(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Logger.java": LOGGER_JAVA,
        "app/Boot.kt": "package app\nimport util.Logger\n"
                       "class Boot { init { Logger.overloaded(\"a\") } }\n",
    })
    assert ("Boot:Boot", "Logger:.overloaded()") in edges


def test_a_class_with_a_property_and_an_init_block_gets_both_edges(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Logger.java": LOGGER_JAVA,
        "app/Both.kt": "package app\nimport util.Logger\n"
                       "class Both {\n    val x = Logger.single(\"a\")\n"
                       "    init { Logger.overloaded(\"b\") }\n}\n",
    })
    assert ("Both:Both", "Logger:.single()") in edges
    assert ("Both:Both", "Logger:.overloaded()") in edges


def test_an_init_block_is_attributed_like_a_property_initializer_in_a_nested_class(tmp_path: Path) -> None:
    # Same shape, once with a property and once with `init`: both must pick the
    # same kind of owner, or the two ways to run code at construction would
    # disagree about who made the call.
    edges = _calls(tmp_path, {
        "util/Logger.java": LOGGER_JAVA,
        "app/ByProp.kt": "package app\nimport util.Logger\n"
                         "class ByProp {\n    class Inner { val x = Logger.single(\"a\") }\n}\n",
        "app/ByInit.kt": "package app\nimport util.Logger\n"
                         "class ByInit {\n    class Inner { init { Logger.single(\"a\") } }\n}\n",
    })
    prop_owner = {s.split(":", 1)[1] for s, t in edges if s.startswith("ByProp:") and t == "Logger:.single()"}
    init_owner = {s.split(":", 1)[1] for s, t in edges if s.startswith("ByInit:") and t == "Logger:.single()"}
    assert prop_owner and prop_owner == init_owner


def test_object_and_companion_init_blocks_produce_an_edge(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Logger.java": LOGGER_JAVA,
        "app/Registry.kt": "package app\nimport util.Logger\n"
                           "object Registry { init { Logger.single(\"a\") } }\n",
        "app/Widget.kt": "package app\nimport util.Logger\n"
                         "class Widget { companion object { init { Logger.single(\"b\") } } }\n",
    })
    assert ("Registry:Registry", "Logger:.single()") in edges
    # The owner of a companion's init is not pinned: the extractor gives the
    # enclosing class or the file node depending on the layout.
    assert any(s.startswith("Widget:") and t == "Logger:.single()" for s, t in edges)


# ---- inherited external methods ----------------------------------------------

def test_an_external_base_does_not_bind_a_bare_call_to_an_unrelated_class(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Prefs.java": PREFS_JAVA,
        "app/Screen.kt": "package app\nimport android.app.Activity\n"
                         "class Screen : Activity() { fun title(): String = getString(1) }\n",
    })
    assert ("Screen:.title()", "Prefs:.getString()") not in edges


def test_a_java_class_with_an_external_base_gets_the_same_guard(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Prefs.java": PREFS_JAVA,
        "app/Screen.java": "package app;\nimport android.app.Activity;\n"
                           "public class Screen extends Activity { public void t() { getString(1); } }\n",
    })
    assert ("Screen:.t()", "Prefs:.getString()") not in edges


def test_an_in_repo_base_that_extends_an_external_class_still_taints_its_children(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Prefs.java": PREFS_JAVA,
        "util/BaseScreen.kt": "package util\nimport android.app.Activity\n"
                              "open class BaseScreen : Activity() { fun baseHelper() {} }\n",
        "app/Screen.kt": "package app\nimport util.BaseScreen\n"
                         "class Screen : BaseScreen() {\n"
                         "    fun a() { baseHelper() }\n"
                         "    fun b(): String = getString(1)\n}\n",
    })
    assert ("Screen:.a()", "BaseScreen:.baseHelper()") in edges      # in-repo member kept
    assert ("Screen:.b()", "Prefs:.getString()") not in edges         # external one dropped


def test_a_top_level_function_is_still_called_from_a_class_with_an_external_base(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Top.kt": "package util\nfun topHelper() {}\n",
        "app/Screen.kt": "package app\nimport android.app.Activity\nimport util.topHelper\n"
                         "class Screen : Activity() { fun t() = topHelper() }\n",
    })
    assert ("Screen:.t()", "Top:topHelper()") in edges


def test_a_member_imported_by_name_survives_an_external_base_in_kotlin(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/Settings.kt": SETTINGS_KT,
        "app/Screen.kt": "package app\nimport android.app.Activity\nimport util.Settings.fetchValue\n"
                         "class Screen : Activity() { fun t() = fetchValue(\"k\") }\n",
    })
    assert ("Screen:.t()", "Settings:.fetchValue()") in edges


def test_a_member_imported_by_name_survives_an_external_base_in_java(tmp_path: Path) -> None:
    edges = _calls(tmp_path, {
        "util/JSettings.java": "package util;\npublic class JSettings { public static void helperJ() {} }\n",
        "app/Screen.java": "package app;\nimport android.app.Activity;\nimport static util.JSettings.helperJ;\n"
                           "public class Screen extends Activity { public void t() { helperJ(); } }\n",
    })
    assert ("Screen:.t()", "JSettings:.helperJ()") in edges
