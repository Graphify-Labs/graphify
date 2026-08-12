"""ActionScript 3 / MXML extraction (Adobe Flex, AIR, Apache Royale).

Beyond the usual declaration coverage, these tests pin three invariants that are
easy to break silently and expensive to notice:

- **Node identity.** A type referenced from several files must land on ONE node.
  graphify's ``_disambiguate_colliding_node_ids`` salts an id with the
  referencing path as soon as one id carries two ``source_file`` values, so a
  reference node has to be attributed to the file that DEFINES the symbol, and a
  shared entity with no defining file has to be marked ``type: "module"``.
  Without both, one event dispatched from N files becomes N nodes.
- **One edge per node pair.** The build is a non-multigraph, so the extractor
  arbitrates rather than emitting edges the build would overwrite.
- **Event identity by value.** Flex couples components by string constant; the
  dispatch side usually writes the literal and the listen side the constant, so
  both must reduce to the same key.
"""
from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from graphify.extract import extract_actionscript, extract_mxml, _make_id


def _write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return path


class ActionScriptTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _edges(result: dict, relation: str) -> list[dict]:
        return [e for e in result["edges"] if e["relation"] == relation]

    @staticmethod
    def _labels(result: dict, relation: str) -> set[str]:
        by_id = {n["id"]: n for n in result["nodes"]}
        return {
            by_id[e["target"]]["label"]
            for e in result["edges"]
            if e["relation"] == relation and e["target"] in by_id
        }


class TestActionScriptDeclarations(ActionScriptTestCase):
    def test_package_imports_inheritance_and_members(self) -> None:
        _write(self.root, "com/example/net/HttpClient.as", """
            package com.example.net {
                public class HttpClient {}
            }
        """)
        _write(self.root, "com/example/net/ITransport.as", """
            package com.example.net {
                public interface ITransport {}
            }
        """)
        target = _write(self.root, "com/example/net/Service.as", """
            package com.example.net
            {
                import flash.events.EventDispatcher;
                import com.example.net.HttpClient;

                public class Service extends EventDispatcher implements ITransport
                {
                    public function send():void {
                        var client:HttpClient = new HttpClient();
                    }
                    public function get busy():Boolean { return false; }
                }
            }
        """)
        result = extract_actionscript(target)

        self.assertIn("EventDispatcher", self._labels(result, "inherits"))
        self.assertIn("ITransport.as", self._labels(result, "implements"))
        self.assertIn("send", self._labels(result, "contains"))
        self.assertIn("busy", self._labels(result, "contains"))
        # The constructor is not a member node: it collides with the file name
        # under any name lookup, and `new Foo()` is already an `instantiates`.
        self.assertNotIn("Service", self._labels(result, "contains"))

    def test_getter_and_setter_pair_yields_one_member(self) -> None:
        target = _write(self.root, "com/example/Config.as", """
            package com.example {
                public class Config {
                    public function get value():String { return _v; }
                    public function set value(v:String):void { _v = v; }
                }
            }
        """)
        result = extract_actionscript(target)
        value_edges = [
            e for e in self._edges(result, "contains")
            if _make_id(_make_id(str(target)), "value") == e["target"]
        ]
        self.assertEqual(len(value_edges), 1)
        self.assertEqual(value_edges[0]["weight"], 2.0)

    def test_comments_do_not_produce_declarations(self) -> None:
        target = _write(self.root, "com/example/Commented.as", """
            package com.example {
                // import com.example.Ghost;
                /* class Phantom extends Nothing { } */
                public class Commented {}
            }
        """)
        result = extract_actionscript(target)
        self.assertEqual(self._labels(result, "imports"), set())
        self.assertEqual(self._labels(result, "inherits"), set())

    def test_line_numbers_survive_comment_blanking(self) -> None:
        target = _write(self.root, "com/example/Lines.as", """
            package com.example {
                /* a
                   multi-line
                   comment */
                import flash.events.Event;
                public class Lines {}
            }
        """)
        result = extract_actionscript(target)
        imports = self._edges(result, "imports")
        self.assertEqual(imports[0]["source_location"], "L5")


class TestNodeIdentity(ActionScriptTestCase):
    def test_reference_and_definition_share_one_node(self) -> None:
        """An import of a corpus type must hit the defining file's own node."""
        definition = _write(self.root, "com/example/util/Tools.as", """
            package com.example.util {
                public class Tools {}
            }
        """)
        consumer_a = _write(self.root, "com/example/a/A.as", """
            package com.example.a {
                import com.example.util.Tools;
                public class A {}
            }
        """)
        consumer_b = _write(self.root, "com/example/b/B.as", """
            package com.example.b {
                import com.example.util.Tools;
                public class B {}
            }
        """)
        defined = extract_actionscript(definition)["nodes"][0]["id"]
        for consumer in (consumer_a, consumer_b):
            result = extract_actionscript(consumer)
            targets = {e["target"] for e in self._edges(result, "imports")}
            self.assertIn(defined, targets)

        # ...and the node each consumer emits for it must be attributed to the
        # defining file, or graphify's disambiguation pass splits it in two.
        for consumer in (consumer_a, consumer_b):
            node = next(
                n for n in extract_actionscript(consumer)["nodes"] if n["id"] == defined
            )
            self.assertEqual(Path(node["source_file"]).name, "Tools.as")

    def test_external_types_are_module_anchors(self) -> None:
        """SDK types have no defining file, so they must be exempt from salting."""
        target = _write(self.root, "com/example/Ext.as", """
            package com.example {
                import flash.events.EventDispatcher;
                public class Ext extends EventDispatcher {}
            }
        """)
        result = extract_actionscript(target)
        external = next(n for n in result["nodes"] if n["label"] == "EventDispatcher")
        self.assertEqual(external.get("type"), "module")

    def test_builtins_are_not_nodes(self) -> None:
        target = _write(self.root, "com/example/Builtins.as", """
            package com.example {
                public class Builtins {
                    public function make():void {
                        var a:Array = new Array();
                        var d:Date = new Date();
                    }
                }
            }
        """)
        result = extract_actionscript(target)
        self.assertEqual(self._labels(result, "instantiates"), set())


class TestEventWiring(ActionScriptTestCase):
    def _corpus(self) -> tuple[Path, Path]:
        publisher = _write(self.root, "com/example/Service.as", """
            package com.example {
                import flash.events.Event;
                import flash.events.EventDispatcher;
                public class Service extends EventDispatcher {
                    public static const LOADED:String = 'service-loaded';
                    public function run():void {
                        dispatchEvent(new Event('service-loaded'));
                    }
                }
            }
        """)
        consumer = _write(self.root, "com/example/Consumer.as", """
            package com.example {
                import com.example.Service;
                public class Consumer {
                    public function bind(s:Service):void {
                        s.addEventListener(Service.LOADED, onLoaded);
                    }
                    private function onLoaded():void {}
                }
            }
        """)
        return publisher, consumer

    def test_literal_dispatch_and_qualified_listen_meet(self) -> None:
        """The whole point: the two halves are written differently, one node."""
        publisher, consumer = self._corpus()
        dispatched = {e["target"] for e in self._edges(extract_actionscript(publisher), "dispatches")}
        listened = {e["target"] for e in self._edges(extract_actionscript(consumer), "listens")}
        self.assertTrue(dispatched, "no dispatch edge extracted")
        self.assertEqual(dispatched, listened)

    def test_event_node_is_keyed_by_value(self) -> None:
        publisher, _ = self._corpus()
        self.assertIn("service-loaded", self._labels(extract_actionscript(publisher), "dispatches"))

    def test_dispatch_and_listen_on_one_pair_becomes_a_relay(self) -> None:
        """A component that emits and subscribes to the same event relays it.

        The build keeps one edge per node pair, so arbitrating between the two
        halves would report a dispatcher with no listener.
        """
        target = _write(self.root, "com/example/Relay.as", """
            package com.example {
                import flash.events.Event;
                import flash.events.EventDispatcher;
                public class Relay extends EventDispatcher {
                    public static const DONE:String = 'done';
                    public function wire(inner:EventDispatcher):void {
                        inner.addEventListener(DONE, onDone);
                    }
                    private function onDone():void {
                        dispatchEvent(new Event(DONE));
                    }
                }
            }
        """)
        result = extract_actionscript(target)
        self.assertIn("done", self._labels(result, "relays"))
        self.assertEqual(self._labels(result, "dispatches"), set())
        self.assertEqual(self._labels(result, "listens"), set())

    def test_application_singleton_access_is_recorded(self) -> None:
        target = _write(self.root, "com/example/Global.as", """
            package com.example {
                import mx.core.FlexGlobals;
                public class Global {
                    public function go():void {
                        FlexGlobals.topLevelApplication.cart.clear();
                        FlexGlobals.topLevelApplication.currentState = 'Home';
                    }
                }
            }
        """)
        result = extract_actionscript(target)
        self.assertIn("cart", self._labels(result, "uses_global"))
        # `currentState` belongs to the Flex Application class, not to the
        # application being analysed, and would be a god node.
        self.assertNotIn("currentState", self._labels(result, "uses_global"))
        # The accessor import itself is redundant with the edges above.
        self.assertNotIn("FlexGlobals", self._labels(result, "imports"))


class TestEdgeArbitration(ActionScriptTestCase):
    def test_stronger_relation_wins_over_imports(self) -> None:
        """The build holds one edge per pair; `imports` is implied by the rest."""
        _write(self.root, "com/example/Base.as", """
            package com.example {
                public class Base {}
            }
        """)
        target = _write(self.root, "com/example/Child.as", """
            package com.example {
                import com.example.Base;
                public class Child extends Base {}
            }
        """)
        result = extract_actionscript(target)
        base_id = _make_id(str(self.root / "com/example/Base.as"))
        relations = {e["relation"] for e in result["edges"] if e["target"] == base_id}
        self.assertEqual(relations, {"inherits"})

    def test_one_edge_per_node_pair(self) -> None:
        target = _write(self.root, "com/example/Many.as", """
            package com.example {
                import flash.events.Event;
                public class Many {
                    public function a():void { dispatchEvent(new Event('x')); }
                    public function b():void { dispatchEvent(new Event('x')); }
                }
            }
        """)
        result = extract_actionscript(target)
        pairs = [(e["source"], e["target"]) for e in result["edges"]]
        self.assertEqual(len(pairs), len(set(pairs)))


class TestMxml(ActionScriptTestCase):
    def test_namespace_tags_script_and_states(self) -> None:
        _write(self.root, "com/example/ui/Widget.mxml", """
            <?xml version="1.0" encoding="utf-8"?>
            <s:Group xmlns:s="library://ns.adobe.com/flex/spark"><fx:Script><![CDATA[]]></fx:Script></s:Group>
        """)
        target = _write(self.root, "Main.mxml", """
            <?xml version="1.0" encoding="utf-8"?>
            <s:WindowedApplication xmlns:fx="http://ns.adobe.com/mxml/2009"
                                   xmlns:s="library://ns.adobe.com/flex/spark"
                                   xmlns:ui="com.example.ui.*">
                <s:states>
                    <s:State name="Home"/>
                    <s:State name="Cart"/>
                </s:states>
                <fx:Script>
                    <![CDATA[
                        import flash.events.Event;
                        private function onReady(e:Event):void {}
                    ]]>
                </fx:Script>
                <ui:Widget includeIn="Cart" id="cart"/>
                <s:Button skinClass="com.example.ui.Widget"
                          icon="@Embed(source='/assets/icon.png')"
                          label="{resourceManager.getString('bundle','LABEL_OK')}"/>
            </s:WindowedApplication>
        """)
        result = extract_mxml(target)

        # xmlns prefix -> package: a tag is a reference with no import line.
        self.assertIn("Widget.mxml", self._labels(result, "instantiates"))
        # The script block is handed to the ActionScript extractor.
        self.assertIn("onReady", self._labels(result, "contains"))
        # View states, and the component that renders one (via includeIn).
        self.assertEqual(self._labels(result, "declares_state"), {"Home", "Cart"})
        self.assertIn("Widget.mxml", self._labels(result, "renders"))
        # Assets and translation keys.
        self.assertIn("icon.png", self._labels(result, "embeds"))
        self.assertIn("LABEL_OK", self._labels(result, "references_i18n"))

    def test_sdk_namespaces_are_not_components(self) -> None:
        target = _write(self.root, "Plain.mxml", """
            <?xml version="1.0" encoding="utf-8"?>
            <s:Group xmlns:fx="http://ns.adobe.com/mxml/2009"
                     xmlns:s="library://ns.adobe.com/flex/spark">
                <s:BorderContainer><s:Label text="hi"/></s:BorderContainer>
            </s:Group>
        """)
        result = extract_mxml(target)
        self.assertEqual(self._labels(result, "instantiates"), set())

    def test_skin_interaction_states_are_excluded(self) -> None:
        """`up`/`over`/`down` describe one component, not the application."""
        target = _write(self.root, "ButtonSkin.mxml", """
            <?xml version="1.0" encoding="utf-8"?>
            <s:SparkSkin xmlns:fx="http://ns.adobe.com/mxml/2009"
                         xmlns:s="library://ns.adobe.com/flex/spark">
                <s:states>
                    <s:State name="up"/>
                    <s:State name="over"/>
                    <s:State name="disabled"/>
                </s:states>
            </s:SparkSkin>
        """)
        result = extract_mxml(target)
        self.assertEqual(self._labels(result, "declares_state"), set())

    def test_unreadable_file_reports_error_without_raising(self) -> None:
        missing = self.root / "Nope.mxml"
        self.assertIn("error", extract_mxml(missing))
        self.assertIn("error", extract_actionscript(self.root / "Nope.as"))


if __name__ == "__main__":
    unittest.main()
