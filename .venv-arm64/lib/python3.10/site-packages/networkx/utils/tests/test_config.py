import collections
import pickle

import pytest

import networkx as nx
from networkx.utils.configs import BackendPriorities, Config


# Define this at module level so we can test pickling
class ExampleConfig(Config):
    """Example configuration."""

    x: int
    y: str

    def _on_setattr(self, key, value):
        if key == "x" and value <= 0:
            raise ValueError("x must be positive")
        if key == "y" and not isinstance(value, str):
            raise TypeError("y must be a str")
        return value


class EmptyConfig(Config):
    pass


@pytest.mark.parametrize("cfg", [EmptyConfig(), Config()])
def test_config_empty(cfg):
    assert dir(cfg) == []
    with pytest.raises(AttributeError):
        cfg.x = 1
    with pytest.raises(KeyError):
        cfg["x"] = 1
    with pytest.raises(AttributeError):
        cfg.x
    with pytest.raises(KeyError):
        cfg["x"]
    assert len(cfg) == 0
    assert "x" not in cfg
    assert cfg == cfg
    assert cfg.get("x", 2) == 2
    assert set(cfg.keys()) == set()
    assert set(cfg.values()) == set()
    assert set(cfg.items()) == set()
    cfg2 = pickle.loads(pickle.dumps(cfg))
    assert cfg == cfg2
    assert isinstance(cfg, collections.abc.Collection)
    assert isinstance(cfg, collections.abc.Mapping)


def test_config_subclass():
    with pytest.raises(TypeError, match="missing 2 required keyword-only"):
        ExampleConfig()
    with pytest.raises(ValueError, match="x must be positive"):
        ExampleConfig(x=0, y="foo")
    with pytest.raises(TypeError, match="unexpected keyword"):
        ExampleConfig(x=1, y="foo", z="bad config")
    with pytest.raises(TypeError, match="unexpected keyword"):
        EmptyConfig(z="bad config")
    cfg = ExampleConfig(x=1, y="foo")
    assert cfg.x == 1
    assert cfg["x"] == 1
    assert cfg["y"] == "foo"
    assert cfg.y == "foo"
    assert "x" in cfg
    assert "y" in cfg
    assert "z" not in cfg
    assert len(cfg) == 2
    assert set(iter(cfg)) == {"x", "y"}
    assert set(cfg.keys()) == {"x", "y"}
    assert set(cfg.values()) == {1, "foo"}
    assert set(cfg.items()) == {("x", 1), ("y", "foo")}
    assert dir(cfg) == ["x", "y"]
    cfg.x = 2
    cfg["y"] = "bar"
    assert cfg["x"] == 2
    assert cfg.y == "bar"
    with pytest.raises(TypeError, match="can't be deleted"):
        del cfg.x
    with pytest.raises(TypeError, match="can't be deleted"):
        del cfg["y"]
    assert cfg.x == 2
    assert cfg == cfg
    assert cfg == ExampleConfig(x=2, y="bar")
    assert cfg != ExampleConfig(x=3, y="baz")
    assert cfg != Config(x=2, y="bar")
    with pytest.raises(TypeError, match="y must be a str"):
        cfg["y"] = 5
    with pytest.raises(ValueError, match="x must be positive"):
        cfg.x = -5
    assert cfg.get("x", 10) == 2
    with pytest.raises(AttributeError):
        cfg.z = 5
    with pytest.raises(KeyError):
        cfg["z"] = 5
    with pytest.raises(AttributeError):
        cfg.z
    with pytest.raises(KeyError):
        cfg["z"]
    cfg2 = pickle.loads(pickle.dumps(cfg))
    assert cfg == cfg2
    assert cfg.__doc__ == "Example configuration."
    assert cfg2.__doc__ == "Example configuration."


def test_config_defaults():
    class DefaultConfig(Config):
        x: int = 0
        y: int

    cfg = DefaultConfig(y=1)
    assert cfg.x == 0
    cfg = DefaultConfig(x=2, y=1)
    assert cfg.x == 2


def test_nxconfig():
    assert isinstance(nx.config.backend_priority, BackendPriorities)
    assert isinstance(nx.config.backend_priority.algos, list)
    assert isinstance(nx.config.backends, Config)
    with pytest.raises(TypeError, match="must be a list of backend names"):
        nx.config.backend_priority.algos = "nx_loopback"
    with pytest.raises(ValueError, match="Unknown backend when setting"):
        nx.config.backend_priority.algos = ["this_almost_certainly_is_not_a_backend"]
    with pytest.raises(TypeError, match="must be a Config of backend configs"):
        nx.config.backends = {}
    with pytest.raises(TypeError, match="must be a Config of backend configs"):
        nx.config.backends = Config(plausible_backend_name={})
    with pytest.raises(ValueError, match="Unknown backend when setting"):
        nx.config.backends = Config(this_almost_certainly_is_not_a_backend=Config())
    with pytest.raises(TypeError, match="must be True or False"):
        nx.config.cache_converted_graphs = "bad value"
    with pytest.raises(TypeError, match="must be a set of "):
        nx.config.warnings_to_ignore = 7
    with pytest.raises(ValueError, match="Unknown warning "):
        nx.config.warnings_to_ignore = {"bad value"}


def test_not_strict():
    class FlexibleConfig(Config, strict=False):
        x: int

    cfg = FlexibleConfig(x=1)
    assert "_strict" not in cfg
    assert len(cfg) == 1
    assert list(cfg) == ["x"]
    assert list(cfg.keys()) == ["x"]
    assert list(cfg.values()) == [1]
    assert list(cfg.items()) == [("x", 1)]
    assert cfg.x == 1
    assert cfg["x"] == 1
    assert "x" in cfg
    assert hasattr(cfg, "x")
    assert "FlexibleConfig(x=1)" in repr(cfg)
    assert cfg == FlexibleConfig(x=1)
    del cfg.x
    assert "FlexibleConfig()" in repr(cfg)
    assert len(cfg) == 0
    assert not hasattr(cfg, "x")
    assert "x" not in cfg
    assert not hasattr(cfg, "y")
    assert "y" not in cfg
    cfg.y = 2
    assert len(cfg) == 1
    assert list(cfg) == ["y"]
    assert list(cfg.keys()) == ["y"]
    assert list(cfg.values()) == [2]
    assert list(cfg.items()) == [("y", 2)]
    assert cfg.y == 2
    assert cfg["y"] == 2
    assert hasattr(cfg, "y")
    assert "y" in cfg
    del cfg["y"]
    assert len(cfg) == 0
    assert list(cfg) == []
    with pytest.raises(AttributeError, match="y"):
        del cfg.y
    with pytest.raises(KeyError, match="y"):
        del cfg["y"]
    with pytest.raises(TypeError, match="missing 1 required keyword-only"):
        FlexibleConfig()
    # Be strict when first creating the config object
    with pytest.raises(TypeError, match="unexpected keyword argument 'y'"):
        FlexibleConfig(x=1, y=2)

    class FlexibleConfigWithDefault(Config, strict=False):
        x: int = 0

    assert FlexibleConfigWithDefault().x == 0
    assert FlexibleConfigWithDefault(x=1)["x"] == 1


def test_context():
    cfg = Config(x=1)
    with cfg(x=2) as c:
        assert c.x == 2
        c.x = 3
        assert cfg.x == 3
    assert cfg.x == 1

    with cfg(x=2) as c:
        assert c == cfg
        assert cfg.x == 2
        with cfg(x=3) as c2:
            assert c2 == cfg
            assert cfg.x == 3
            with pytest.raises(RuntimeError, match="context manager without"):
                with cfg as c3:  # Forgot to call `cfg(...)`
                    pass
            assert cfg.x == 3
        assert cfg.x == 2
    assert cfg.x == 1

    c = cfg(x=4)  # Not yet as context (not recommended, but possible)
    assert c == cfg
    assert cfg.x == 4
    # Cheat by looking at internal data; context stack should only grow with __enter__
    assert cfg._prev is not None
    assert cfg._context_stack == []
    with c:
        assert c == cfg
        assert cfg.x == 4
    assert cfg.x == 1
    # Cheat again; there was no preceding `cfg(...)` call this time
    assert cfg._prev is None
    with pytest.raises(RuntimeError, match="context manager without"):
        with cfg:
            pass
    assert cfg.x == 1
