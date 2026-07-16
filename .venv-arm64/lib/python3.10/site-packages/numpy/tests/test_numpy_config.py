"""
Check the numpy config is valid.
"""
import numpy as np
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.skipif(
    not hasattr(np.__config__, "_built_with_meson"),
    reason="Requires Meson builds",
)


class TestNumPyConfigs:
    REQUIRED_CONFIG_KEYS = [
        "Compilers",
        "Machine Information",
        "Python Information",
    ]

    @patch("numpy.__config__._check_pyyaml")
    def test_pyyaml_not_found(self, mock_yaml_importer):
        mock_yaml_importer.side_effect = ModuleNotFoundError()
        with pytest.warns(UserWarning):
            np.show_config()

    def test_dict_mode(self):
        config = np.show_config(mode="dicts")

        assert isinstance(config, dict)
        assert all(key in config for key in self.REQUIRED_CONFIG_KEYS), (
            "Required key missing,"
            " see index of `False` with `REQUIRED_CONFIG_KEYS`"
        )

    def test_invalid_mode(self):
        with pytest.raises(AttributeError):
            np.show_config(mode="foo")

    def test_warn_to_add_tests(self):
        assert len(np.__config__.DisplayModes) == 2, (
            "New mode detected,"
            " please add UT if applicable and increment this count"
        )
