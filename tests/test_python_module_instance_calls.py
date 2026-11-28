"""Module singletons must resolve without inventing edges for shadowed names."""
import pytest

from graphify.extract import extract


def _extract(tmp_path, source, service="Svc"):
    package = tmp_path / "pkg"
    package.mkdir(exist_ok=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "service.py").write_text(
        f"class {service}:\n    def create(self): return 1\n", encoding="utf-8"
    )
    (package / "caller.py").write_text(source, encoding="utf-8")
    result = extract(sorted(package.glob("*.py")), root=tmp_path,
                     cache_root=tmp_path / "graphify-out", parallel=False)
    nodes = {node["id"]: node for node in result["nodes"]}
    return [edge for edge in result["edges"]
            if edge["relation"] == "calls"
            and nodes[edge["source"]]["label"] == "run()"
            and nodes[edge["target"]]["label"] == ".create()"]


@pytest.mark.parametrize("service,instance", [("Svc", "g"), ("lower_svc", "lower_svc"),
                                             ("Svc", "GLOBAL")])
def test_module_constructor_instance(tmp_path, service, instance):
    source = (f"from .service import {service}\n{instance} = {service}()\n"
              f"def run(): return {instance}.create()\n")
    cold = _extract(tmp_path, source, service)
    warm = _extract(tmp_path, source, service)
    assert len(cold) == 1
    assert cold[0]["confidence"] == "INFERRED"
    assert warm == cold


@pytest.mark.parametrize("body", [
    "def run(g): return g.create()\n",
    "def run():\n    g = other()\n    return g.create()\n",
    "def outer(g):\n    def run(): return g.create()\n",
    "def run():\n    for g in []: g.create()\n",
    "def run():\n    del g\n    return g.create()\n",
])
def test_local_binding_shadows_module_instance(tmp_path, body):
    assert not _extract(tmp_path, "from .service import Svc\ng = Svc()\n" + body)


@pytest.mark.parametrize("extra", [
    "g = other()\n", "del g\n", "for g in []: pass\n",
    "def g(): pass\n", "import g\n",
    "def replace():\n    global g\n    g = other()\n",
])
def test_rebound_module_instance_is_unresolved(tmp_path, extra):
    assert not _extract(tmp_path, "from .service import Svc\ng = Svc()\n" + extra
                        + "def run(): return g.create()\n")


def test_rebound_constructor_is_unresolved(tmp_path):
    assert not _extract(tmp_path, "from .service import Svc\nSvc = other\ng = Svc()\n"
                        "def run(): return g.create()\n")


def test_imported_class_alias(tmp_path):
    assert len(_extract(tmp_path, "from .service import Svc as Alias\ng = Alias()\n"
                        "def run(): return g.create()\n")) == 1


def test_same_file_lowercase_class(tmp_path):
    assert len(_extract(tmp_path, "class local_svc:\n    def create(self): return 2\n"
                        "local_svc = local_svc()\ndef run(): return local_svc.create()\n")) == 1


@pytest.mark.parametrize("source", [
    "from .service import Svc\nif flag: g = Svc()\ndef run(): return g.create()\n",
    "from .service import Svc\ng = Svc()\nglobals()['g'] = other\n"
    "def run(): return g.create()\n",
    "from .service import Svc\ng = Svc()\nfrom .other import *\n"
    "def run(): return g.create()\n",
    "from .service import Svc\ng = Svc()\nwith other() as g: pass\n"
    "def run(): return g.create()\n",
    "from .service import Svc\ng = Svc()\n"
    "def run():\n    try: pass\n    except Exception as g: g.create()\n",
])
def test_uncertain_module_bindings_are_unresolved(tmp_path, source):
    assert not _extract(tmp_path, source)
