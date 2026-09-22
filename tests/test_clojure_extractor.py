"""Extraction coverage for clojure."""
from __future__ import annotations

import sys
from pathlib import Path

from graphify.extract import extract

FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.clj"


def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


def _kinds(result: dict) -> dict[str, str]:
    return {node["label"]: node["metadata"].get("kind") for node in result["nodes"]}


def test_clojure_definitions_and_local_calls(tmp_path):
    source = tmp_path / "core.clj"
    source.write_text(
        "(ns app.core)\n"
        "(def ^:private limit 10)\n"
        "(defonce state (atom {}))\n"
        "(def shout (fn [s] (str s \"!\")))\n"
        "(defn- helper [x] (inc x))\n"
        "(defn greet\n"
        "  ([name] (greet name \"Hi\"))\n"
        "  ([name greeting] (helper (count name)) (shout greeting)))\n"
        "(defmacro unless [c & body] `(if (not ~c) (do ~@body)))\n"
        "(defmulti speak :kind)\n"
        "(defmethod speak :dog [_] (greet \"dog\"))\n"
        "(defn main [& args] (map helper args) (unless false (greet \"x\")))\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    kinds = _kinds(result)
    assert kinds["app.core"] == "namespace"
    assert kinds["limit"] == "var"
    assert kinds["state"] == "var"
    assert kinds["shout"] == "var"
    assert kinds["helper"] == "function"
    assert kinds["greet"] == "function"
    assert kinds["unless"] == "macro"
    assert kinds["speak"] == "multimethod"
    assert kinds["speak :dog"] == "method"

    callable_labels = {node["label"] for node in result["nodes"] if node.get("_callable")}
    assert {"shout", "helper", "greet", "unless", "main"} <= callable_labels
    assert "limit" not in callable_labels

    contains = _edge_labels(result, "contains")
    assert ("core.clj", "app.core") in contains
    assert ("app.core", "greet") in contains

    calls = _edge_labels(result, "calls")
    assert ("greet", "helper") in calls
    assert ("greet", "shout") in calls
    assert ("speak :dog", "greet") in calls
    assert ("main", "greet") in calls
    assert ("main", "unless") in calls
    # higher-order use: helper passed as a value to map
    assert ("main", "helper") in calls
    # recursion is not a self-edge
    assert ("greet", "greet") not in calls
    assert ("speak :dog", "speak") in _edge_labels(result, "implements")


def test_clojure_protocols_records_and_java_imports(tmp_path):
    source = tmp_path / "shapes.clj"
    source.write_text(
        "(ns app.shapes\n"
        "  (:import (java.util Date UUID) java.io.File))\n"
        "(defprotocol Shape\n"
        "  (area [this])\n"
        "  (perimeter [this]))\n"
        "(defrecord Circle [r]\n"
        "  Shape\n"
        "  (area [_] (* Math/PI r r))\n"
        "  (perimeter [_] (* 2 Math/PI r)))\n"
        "(deftype Point [x y])\n"
        "(extend-protocol Shape\n"
        "  Point\n"
        "  (area [_] 0)\n"
        "  String\n"
        "  (area [s] (count s)))\n"
        "(defn total [shapes] (reduce + (map area shapes)))\n"
        "(defn make [] (->Circle 1) (map->Circle {:r 2}) (Date.) (UUID/randomUUID))\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    kinds = _kinds(result)
    assert kinds["Shape"] == "protocol"
    assert kinds["area"] == "protocol_method"
    assert kinds["Circle"] == "record"
    assert kinds["Circle/area"] == "method"
    assert kinds["Point"] == "type"
    assert kinds["Point/area"] == "method"
    assert kinds["String/area"] == "method"
    assert kinds["java.util.Date"] == "class"
    assert kinds["java.util.UUID"] == "class"
    assert kinds["java.io.File"] == "class"

    implements = _edge_labels(result, "implements")
    assert ("Circle", "Shape") in implements
    assert ("Point", "Shape") in implements
    assert ("String", "Shape") in implements

    imports = _edge_labels(result, "imports")
    assert ("app.shapes", "java.util.Date") in imports
    assert ("app.shapes", "java.io.File") in imports

    contains = _edge_labels(result, "contains")
    assert ("Shape", "area") in contains
    assert ("Circle", "Circle/area") in contains

    assert ("total", "area") in _edge_labels(result, "calls")
    assert ("make", "Circle") in _edge_labels(result, "references")

    # Java interop is never a call edge to user code
    labels = {node["label"] for node in result["nodes"]}
    assert "Math" not in labels
    assert "randomUUID" not in labels


def test_clojure_requires_resolve_across_namespaces(tmp_path):
    (tmp_path / "app").mkdir()
    util = tmp_path / "app" / "util.clj"
    util.write_text(
        "(ns app.util)\n"
        "(defn helper [x] x)\n"
        "(defn other [] 1)\n"
        "(defn shared [] 2)\n",
        encoding="utf-8",
    )
    text = tmp_path / "app" / "text.cljc"
    text.write_text(
        "(ns app.text)\n(defn fmt [s] s)\n(defn shared [] 3)\n", encoding="utf-8"
    )
    core = tmp_path / "app" / "core.clj"
    core.write_text(
        "(ns app.core\n"
        "  (:require [app.util :as u :refer [helper]]\n"
        "            [app.text :refer :all]\n"
        "            [clojure.string :as str]\n"
        "            [clojure [set :as set]]))\n"
        "(defn run [x]\n"
        "  (helper x)\n"
        "  (u/other)\n"
        "  (fmt x)\n"
        "  (shared)\n"
        "  (app.util/other)\n"
        "  (str/join \",\" [x])\n"
        "  (set/union #{} #{}))\n",
        encoding="utf-8",
    )

    result = extract([core, util, text], cache_root=tmp_path)

    imports = _edge_labels(result, "imports")
    assert ("app.core", "app.util") in imports
    assert ("app.core", "app.text") in imports
    # external namespaces become a single non-source-backed node each
    assert ("app.core", "clojure.string") in imports
    assert ("app.core", "clojure.set") in imports
    externals = [
        node for node in result["nodes"]
        if node["label"] in {"clojure.string", "clojure.set"}
    ]
    assert len(externals) == 2
    assert all("source_file" not in node for node in externals)
    assert all(node["metadata"].get("external") for node in externals)

    calls = _edge_labels(result, "calls")
    assert ("run", "helper") in calls      # :refer
    assert ("run", "other") in calls       # alias/ and fully-qualified
    assert ("run", "fmt") in calls         # :refer :all
    # `shared` exists in app.util (not referred) and app.text (:refer :all):
    # only the referred namespace is a candidate, so it resolves.
    assert ("run", "shared") in calls
    # no edge into clojure.string / clojure.set — they are not in the corpus
    assert not any(target in {"join", "union"} for _, target in calls)


def test_clojure_ambiguous_refer_all_does_not_resolve(tmp_path):
    a = tmp_path / "a.clj"
    a.write_text("(ns a)\n(defn thing [] 1)\n", encoding="utf-8")
    b = tmp_path / "b.clj"
    b.write_text("(ns b)\n(defn thing [] 2)\n", encoding="utf-8")
    core = tmp_path / "core.clj"
    core.write_text(
        "(ns core (:use a b))\n(defn run [] (thing))\n", encoding="utf-8"
    )

    result = extract([core, a, b], cache_root=tmp_path)

    assert ("run", "thing") not in _edge_labels(result, "calls")
    assert ("core", "a") in _edge_labels(result, "imports")
    assert ("core", "b") in _edge_labels(result, "imports")


def test_clojure_custom_definers_and_top_level_require(tmp_path):
    lib = tmp_path / "lib.clj"
    lib.write_text("(ns lib)\n(defn target [] 1)\n", encoding="utf-8")
    source = tmp_path / "core_test.clj"
    source.write_text(
        "(ns core-test)\n"
        "(require '[lib :as l])\n"
        "(defn setup [] 1)\n"
        "(deftest my-test (setup) (l/target))\n"
        "(defroutes app (setup))\n"
        "(run-tests)\n",
        encoding="utf-8",
    )

    result = extract([source, lib], cache_root=tmp_path)

    kinds = _kinds(result)
    assert kinds["my-test"] == "definition"
    assert kinds["app"] == "definition"
    definers = {
        node["label"]: node["metadata"].get("definer") for node in result["nodes"]
    }
    assert definers["my-test"] == "deftest"
    assert definers["app"] == "defroutes"

    calls = _edge_labels(result, "calls")
    assert ("my-test", "setup") in calls
    assert ("app", "setup") in calls
    assert ("my-test", "target") in calls
    assert ("core-test", "lib") in _edge_labels(result, "imports")


def test_clojure_edn_files_are_data_only(tmp_path):
    deps = tmp_path / "deps.edn"
    deps.write_text(
        "{:paths [\"src\"]\n :deps {org.clojure/clojure {:mvn/version \"1.11.1\"}}}\n",
        encoding="utf-8",
    )

    result = extract([deps], cache_root=tmp_path)

    assert [node["label"] for node in result["nodes"]] == ["deps.edn"]
    assert result["edges"] == []


def test_clojure_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"sample", "run", "helper"} <= labels
    assert ("run", "helper") in _edge_labels(result, "calls")


def test_clojure_malformed_source_and_comments_do_not_create_phantoms(tmp_path):
    source = tmp_path / "broken.clj"
    source.write_text(
        "(ns broken)\n"
        "(defn valid [] :ok)\n"
        ";; (defn ghost [] :boo)\n"
        "(comment (defn also-ghost [] 1))\n"
        "#_(defn discarded [] 1)\n"
        "(defn broken-fn [x\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert "valid" in labels
    assert labels.isdisjoint({"ghost", "also-ghost", "discarded"})


def test_clojure_missing_parser_reports_install_hint(tmp_path, monkeypatch, capsys):
    source = tmp_path / "missing.clj"
    source.write_text("(ns missing)\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "tree_sitter_language_pack", None)

    result = extract([source], cache_root=tmp_path)

    assert result["nodes"] == []
    assert 'pip install "graphifyy[clojure]"' in capsys.readouterr().err


def test_clojure_operator_symbols_get_distinct_ids(tmp_path):
    source = tmp_path / "ops.clj"
    source.write_text(
        "(ns ops)\n"
        "(defn <!! [port] port)\n"
        "(defn >!! [port val] val)\n"
        "(defn valid? [x] x)\n"
        "(defn valid! [x] x)\n"
        "(defn valid [x] x)\n"
        "(defn run [p] (<!! p) (>!! p 1) (valid? p) (valid! p) (valid p))\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = [node["label"] for node in result["nodes"]]
    assert {"<!!", ">!!", "valid?", "valid!", "valid"} <= set(labels)
    assert len(labels) == len(set(labels))
    calls = _edge_labels(result, "calls")
    assert {("run", "<!!"), ("run", ">!!"), ("run", "valid?"), ("run", "valid!"), ("run", "valid")} <= calls


def test_clojure_calls_resolve_to_protocol_method_not_implementations(tmp_path):
    store = tmp_path / "store.clj"
    store.write_text(
        "(ns app.store)\n"
        "(defprotocol Store\n"
        "  (read-item [store k]))\n"
        "(defrecord MemoryStore [m]\n"
        "  Store\n"
        "  (read-item [_ k] (get m k)))\n"
        "(defrecord NullStore []\n"
        "  Store\n"
        "  (read-item [_ _] nil))\n",
        encoding="utf-8",
    )
    core = tmp_path / "core.clj"
    core.write_text(
        "(ns app.core (:require [app.store :as store]))\n"
        "(defn fetch [s k] (store/read-item s k))\n",
        encoding="utf-8",
    )

    result = extract([core, store], cache_root=tmp_path)

    kinds_by_id = {node["id"]: node["metadata"].get("kind") for node in result["nodes"]}
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    targets = [
        (labels[edge["target"]], kinds_by_id[edge["target"]])
        for edge in result["edges"]
        if edge["relation"] == "calls" and labels[edge["source"]] == "fetch"
    ]
    assert targets == [("read-item", "protocol_method")]
    assert {"MemoryStore/read-item", "NullStore/read-item"} <= set(labels.values())


def test_clojure_namespaced_and_nested_definers(tmp_path):
    source = tmp_path / "ui.cljs"
    source.write_text(
        "(ns app.ui (:require [helix.core :as helix] [cljs.test :as t]))\n"
        "(defn render [] 1)\n"
        "(helix/defnc button [props] (render))\n"
        "(t/deftest button-test (render))\n"
        "(if-not goog.DEBUG\n"
        "  (defn debug-cell [title c] [])\n"
        "  (defn debug-cell [title c] (render)))\n"
        "(when true\n"
        "  (def enabled? true)\n"
        "  (render))\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    kinds = _kinds(result)
    assert kinds["button"] == "definition"
    assert kinds["button-test"] == "definition"
    assert kinds["debug-cell"] == "function"
    assert kinds["enabled?"] == "var"
    definers = {
        node["label"]: node["metadata"].get("definer") for node in result["nodes"]
    }
    assert definers["button"] == "helix/defnc"
    assert definers["button-test"] == "t/deftest"

    calls = _edge_labels(result, "calls")
    assert ("button", "render") in calls
    assert ("button-test", "render") in calls
    assert ("debug-cell", "render") in calls
    # the bare `(render)` inside `when` belongs to the namespace, and the nested
    # def bodies are not double-attributed to it
    assert ("app.ui", "render") in calls
    assert ("app.ui", "debug-cell") not in calls


def test_clojure_aliased_record_constructor_resolves_across_namespaces(tmp_path):
    store = tmp_path / "store.clj"
    store.write_text("(ns app.store)\n(defrecord Batch [ops])\n", encoding="utf-8")
    core = tmp_path / "core.clj"
    core.write_text(
        "(ns app.core (:require [app.store :as store]))\n"
        "(defn run [] (store/->Batch []) (store/map->Batch {}))\n",
        encoding="utf-8",
    )

    result = extract([core, store], cache_root=tmp_path)

    assert ("run", "Batch") in _edge_labels(result, "references")
    assert not any(target == "Batch" for _, target in _edge_labels(result, "calls"))


def test_clojure_protocol_with_docstrings_and_metadata_keeps_its_methods(tmp_path):
    source = tmp_path / "protocols.clj"
    source.write_text(
        "(ns app.protocols)\n"
        "(defprotocol ^{:added \"1.6\"} Streamable\n"
        "  \"A protocol docstring.\"\n"
        "  (write-body [body out] \"method docstring\")\n"
        "  (close-body [body]))\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    kinds = _kinds(result)
    assert kinds["Streamable"] == "protocol"
    assert kinds["write-body"] == "protocol_method"
    assert kinds["close-body"] == "protocol_method"
    assert ("Streamable", "write-body") in _edge_labels(result, "contains")
