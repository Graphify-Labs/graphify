import os
import re
import sys
import pathlib
import platform
import subprocess
import pytest
from numpy._core._multiarray_umath import (
    __cpu_features__,
    __cpu_baseline__,
    __cpu_dispatch__,
)
import numpy as np

def assert_features_equal(actual, desired, fname):
    __tracebackhide__ = True  # Hide traceback for py.test
    actual, desired = str(actual), str(desired)
    if actual == desired:
        return
    detected = str(__cpu_features__).replace("'", "")
    try:
        with open("/proc/cpuinfo") as fd:
            cpuinfo = fd.read(2048)
    except Exception as err:
        cpuinfo = str(err)

    try:
        import subprocess
        auxv = subprocess.check_output(['/bin/true'], env=dict(LD_SHOW_AUXV="1"))
        auxv = auxv.decode()
    except Exception as err:
        auxv = str(err)

    import textwrap
    error_report = textwrap.indent(
"""
###########################################
### Extra debugging information
###########################################
-------------------------------------------
--- NumPy Detections
-------------------------------------------
%s
-------------------------------------------
--- SYS / CPUINFO
-------------------------------------------
%s....
-------------------------------------------
--- SYS / AUXV
-------------------------------------------
%s
""" % (detected, cpuinfo, auxv), prefix='\r')

    raise AssertionError((
        "Failure Detection\n"
        " NAME: '%s'\n"
        " ACTUAL: %s\n"
        " DESIRED: %s\n"
        "%s"
    ) % (fname, actual, desired, error_report))

def _text_to_list(txt):
    out = txt.strip("][\n").replace("'", "").split(', ')
    return None if out[0] == "" else out

class AbstractTest:
    features = []
    features_groups = {}
    features_map = {}
    features_flags = set()

    def load_flags(self):
        # a hook
        pass
    def test_features(self):
        self.load_flags()
        for gname, features in self.features_groups.items():
            test_features = [self.cpu_have(f) for f in features]
            assert_features_equal(__cpu_features__.get(gname), all(test_features), gname)

        for feature_name in self.features:
            cpu_have = self.cpu_have(feature_name)
            npy_have = __cpu_features__.get(feature_name)
            assert_features_equal(npy_have, cpu_have, feature_name)

    def cpu_have(self, feature_name):
        map_names = self.features_map.get(feature_name, feature_name)
        if isinstance(map_names, str):
            return map_names in self.features_flags
        return any(f in self.features_flags for f in map_names)

    def load_flags_cpuinfo(self, magic_key):
        self.features_flags = self.get_cpuinfo_item(magic_key)

    def get_cpuinfo_item(self, magic_key):
        values = set()
        with open('/proc/cpuinfo') as fd:
            for line in fd:
                if not line.startswith(magic_key):
                    continue
                flags_value = [s.strip() for s in line.split(':', 1)]
                if len(flags_value) == 2:
                    values = values.union(flags_value[1].upper().split())
        return values

    def load_flags_auxv(self):
        auxv = subprocess.check_output(['/bin/true'], env=dict(LD_SHOW_AUXV="1"))
        for at in auxv.split(b'\n'):
            if not at.startswith(b"AT_HWCAP"):
                continue
            hwcap_value = [s.strip() for s in at.split(b':', 1)]
            if len(hwcap_value) == 2:
                self.features_flags = self.features_flags.union(
                    hwcap_value[1].upper().decode().split()
                )

@pytest.mark.skipif(
    sys.platform == 'emscripten',
    reason= (
        "The subprocess module is not available on WASM platforms and"
        " therefore this test class cannot be properly executed."
    ),
)
class TestEnvPrivation:
    cwd = pathlib.Path(__file__).parent.resolve()
    env = os.environ.copy()
    _enable = os.environ.pop('NPY_ENABLE_CPU_FEATURES', None)
    _disable = os.environ.pop('NPY_DISABLE_CPU_FEATURES', None)
    SUBPROCESS_ARGS = dict(cwd=cwd, capture_output=True, text=True, check=True)
    unavailable_feats = [
        feat for feat in __cpu_dispatch__ if not __cpu_features__[feat]
    ]
    UNAVAILABLE_FEAT = (
        None if len(unavailable_feats) == 0
        else unavailable_feats[0]
    )
    BASELINE_FEAT = None if len(__cpu_baseline__) == 0 else __cpu_baseline__[0]
    SCRIPT = """
def main():
    from numpy._core._multiarray_umath import (
        __cpu_features__,
        __cpu_dispatch__
    )

    detected = [feat for feat in __cpu_dispatch__ if __cpu_features__[feat]]
    print(detected)

if __name__ == "__main__":
    main()
    """

    @pytest.fixture(autouse=True)
    def setup_class(self, tmp_path_factory):
        file = tmp_path_factory.mktemp("runtime_test_script")
        file /= "_runtime_detect.py"
        file.write_text(self.SCRIPT)
        self.file = file
        return

    def _run(self):
        return subprocess.run(
            [sys.executable, self.file],
            env=self.env,
            **self.SUBPROCESS_ARGS,
            )

    # Helper function mimicking pytest.raises for subprocess call
    def _expect_error(
        self,
        msg,
        err_type,
        no_error_msg="Failed to generate error"
    ):
        try:
            self._run()
        except subprocess.CalledProcessError as e:
            assertion_message = f"Expected: {msg}\nGot: {e.stderr}"
            assert re.search(msg, e.stderr), assertion_message

            assertion_message = (
                f"Expected error of type: {err_type}; see full "
                f"error:\n{e.stderr}"
            )
            assert re.search(err_type, e.stderr), assertion_message
        else:
            assert False, no_error_msg

    def setup_method(self):
        """Ensure that the environment is reset"""
        self.env = os.environ.copy()
        return

    def test_runtime_feature_selection(self):
        """
        Ensure that when selecting `NPY_ENABLE_CPU_FEATURES`, only the
        features exactly specified are dispatched.
        """

        # Capture runtime-enabled features
        out = self._run()
        non_baseline_features = _text_to_list(out.stdout)

        if non_baseline_features is None:
            pytest.skip(
                "No dispatchable features outside of baseline detected."
            )
        feature = non_baseline_features[0]

        # Capture runtime-enabled features when `NPY_ENABLE_CPU_FEATURES` is
        # specified
        self.env['NPY_ENABLE_CPU_FEATURES'] = feature
        out = self._run()
        enabled_features = _text_to_list(out.stdout)

        # Ensure that only one feature is enabled, and it is exactly the one
        # specified by `NPY_ENABLE_CPU_FEATURES`
        assert set(enabled_features) == {feature}

        if len(non_baseline_features) < 2:
            pytest.skip("Only one non-baseline feature detected.")
        # Capture runtime-enabled features when `NPY_ENABLE_CPU_FEATURES` is
        # specified
        self.env['NPY_ENABLE_CPU_FEATURES'] = ",".join(non_baseline_features)
        out = self._run()
        enabled_features = _text_to_list(out.stdout)

        # Ensure that both features are enabled, and they are exactly the ones
        # specified by `NPY_ENABLE_CPU_FEATURES`
        assert set(enabled_features) == set(non_baseline_features)
        return

    @pytest.mark.parametrize("enabled, disabled",
    [
        ("feature", "feature"),
        ("feature", "same"),
    ])
    def test_both_enable_disable_set(self, enabled, disabled):
        """
        Ensure that when both environment variables are set then an
        ImportError is thrown
        """
        self.env['NPY_ENABLE_CPU_FEATURES'] = enabled
        self.env['NPY_DISABLE_CPU_FEATURES'] = disabled
        msg = "Both NPY_DISABLE_CPU_FEATURES and NPY_ENABLE_CPU_FEATURES"
        err_type = "ImportError"
        self._expect_error(msg, err_type)

    @pytest.mark.skipif(
        not __cpu_dispatch__,
        reason=(
            "NPY_*_CPU_FEATURES only parsed if "
            "`__cpu_dispatch__` is non-empty"
        )
    )
    @pytest.mark.parametrize("action", ["ENABLE", "DISABLE"])
    def test_variable_too_long(self, action):
        """
        Test that an error is thrown if the environment variables are too long
        to be processed. Current limit is 1024, but this may change later.
        """
        MAX_VAR_LENGTH = 1024
        # Actual length is MAX_VAR_LENGTH + 1 due to null-termination
        self.env[f'NPY_{action}_CPU_FEATURES'] = "t" * MAX_VAR_LENGTH
        msg = (
            f"Length of environment variable 'NPY_{action}_CPU_FEATURES' is "
            f"{MAX_VAR_LENGTH + 1}, only {MAX_VAR_LENGTH} accepted"
        )
        err_type = "RuntimeError"
        self._expect_error(msg, err_type)

    @pytest.mark.skipif(
        not __cpu_dispatch__,
        reason=(
            "NPY_*_CPU_FEATURES only parsed if "
            "`__cpu_dispatch__` is non-empty"
        )
    )
    def test_impossible_feature_disable(self):
        """
        Test that a RuntimeError is thrown if an impossible feature-disabling
        request is made. This includes disabling a baseline feature.
        """

        if self.BASELINE_FEAT is None:
            pytest.skip("There are no unavailable features to test with")
        bad_feature = self.BASELINE_FEAT
        self.env['NPY_DISABLE_CPU_FEATURES'] = bad_feature
        msg = (
            f"You cannot disable CPU feature '{bad_feature}', since it is "
            "part of the baseline optimizations"
        )
        err_type = "RuntimeError"
        self._expect_error(msg, err_type)

    def test_impossible_feature_enable(self):
        """
        Test that a RuntimeError is thrown if an impossible feature-enabling
        request is made. This includes enabling a feature not supported by the
        machine, or disabling a baseline optimization.
        """

        if self.UNAVAILABLE_FEAT is None:
            pytest.skip("There are no unavailable features to test with")
        bad_feature = self.UNAVAILABLE_FEAT
        self.env['NPY_ENABLE_CPU_FEATURES'] = bad_feature
        msg = (
            f"You cannot enable CPU features \\({bad_feature}\\), since "
            "they are not supported by your machine."
        )
        err_type = "RuntimeError"
        self._expect_error(msg, err_type)

        # Ensure that it fails even when providing garbage in addition
        feats = f"{bad_feature}, Foobar"
        self.env['NPY_ENABLE_CPU_FEATURES'] = feats
        msg = (
            f"You cannot enable CPU features \\({bad_feature}\\), since they "
            "are not supported by your machine."
        )
        self._expect_error(msg, err_type)

        if self.BASELINE_FEAT is not None:
            # Ensure that only the bad feature gets reported
            feats = f"{bad_feature}, {self.BASELINE_FEAT}"
            self.env['NPY_ENABLE_CPU_FEATURES'] = feats
            msg = (
                f"You cannot enable CPU features \\({bad_feature}\\), since "
                "they are not supported by your machine."
            )
            self._expect_error(msg, err_type)

is_linux = sys.platform.startswith('linux')
is_cygwin = sys.platform.startswith('cygwin')
machine  = platform.machine()
is_x86   = re.match("^(amd64|x86|i386|i686)", machine, re.IGNORECASE)
@pytest.mark.skipif(
    not (is_linux or is_cygwin) or not is_x86, reason="Only for Linux and x86"
)
class Test_X86_Features(AbstractTest):
    features = [
        "MMX", "SSE", "SSE2", "SSE3", "SSSE3", "SSE41", "POPCNT", "SSE42",
        "AVX", "F16C", "XOP", "FMA4", "FMA3", "AVX2", "AVX512F", "AVX512CD",
        "AVX512ER", "AVX512PF", "AVX5124FMAPS", "AVX5124VNNIW", "AVX512VPOPCNTDQ",
        "AVX512VL", "AVX512BW", "AVX512DQ", "AVX512VNNI", "AVX512IFMA",
        "AVX512VBMI", "AVX512VBMI2", "AVX512BITALG", "AVX512FP16",
    ]
    features_groups = dict(
        AVX512_KNL = ["AVX512F", "AVX512CD", "AVX512ER", "AVX512PF"],
        AVX512_KNM = ["AVX512F", "AVX512CD", "AVX512ER", "AVX512PF", "AVX5124FMAPS",
                      "AVX5124VNNIW", "AVX512VPOPCNTDQ"],
        AVX512_SKX = ["AVX512F", "AVX512CD", "AVX512BW", "AVX512DQ", "AVX512VL"],
        AVX512_CLX = ["AVX512F", "AVX512CD", "AVX512BW", "AVX512DQ", "AVX512VL", "AVX512VNNI"],
        AVX512_CNL = ["AVX512F", "AVX512CD", "AVX512BW", "AVX512DQ", "AVX512VL", "AVX512IFMA",
                      "AVX512VBMI"],
        AVX512_ICL = ["AVX512F", "AVX512CD", "AVX512BW", "AVX512DQ", "AVX512VL", "AVX512IFMA",
                      "AVX512VBMI", "AVX512VNNI", "AVX512VBMI2", "AVX512BITALG", "AVX512VPOPCNTDQ"],
        AVX512_SPR = ["AVX512F", "AVX512CD", "AVX512BW", "AVX512DQ",
                      "AVX512VL", "AVX512IFMA", "AVX512VBMI", "AVX512VNNI",
                      "AVX512VBMI2", "AVX512BITALG", "AVX512VPOPCNTDQ",
                      "AVX512FP16"],
    )
    features_map = dict(
        SSE3="PNI", SSE41="SSE4_1", SSE42="SSE4_2", FMA3="FMA",
        AVX512VNNI="AVX512_VNNI", AVX512BITALG="AVX512_BITALG", AVX512VBMI2="AVX512_VBMI2",
        AVX5124FMAPS="AVX512_4FMAPS", AVX5124VNNIW="AVX512_4VNNIW", AVX512VPOPCNTDQ="AVX512_VPOPCNTDQ",
        AVX512FP16="AVX512_FP16",
    )
    def load_flags(self):
        self.load_flags_cpuinfo("flags")

is_power = re.match("^(powerpc|ppc)64", machine, re.IGNORECASE)
@pytest.mark.skipif(not is_linux or not is_power, reason="Only for Linux and Power")
class Test_POWER_Features(AbstractTest):
    features = ["VSX", "VSX2", "VSX3", "VSX4"]
    features_map = dict(VSX2="ARCH_2_07", VSX3="ARCH_3_00", VSX4="ARCH_3_1")

    def load_flags(self):
        self.load_flags_auxv()


is_zarch = re.match("^(s390x)", machine, re.IGNORECASE)
@pytest.mark.skipif(not is_linux or not is_zarch,
                    reason="Only for Linux and IBM Z")
class Test_ZARCH_Features(AbstractTest):
    features = ["VX", "VXE", "VXE2"]

    def load_flags(self):
        self.load_flags_auxv()


is_arm = re.match("^(arm|aarch64)", machine, re.IGNORECASE)
@pytest.mark.skipif(not is_linux or not is_arm, reason="Only for Linux and ARM")
class Test_ARM_Features(AbstractTest):
    features = [
        "SVE", "NEON", "ASIMD", "FPHP", "ASIMDHP", "ASIMDDP", "ASIMDFHM"
    ]
    features_groups = dict(
        NEON_FP16  = ["NEON", "HALF"],
        NEON_VFPV4 = ["NEON", "VFPV4"],
    )
    def load_flags(self):
        self.load_flags_cpuinfo("Features")
        arch = self.get_cpuinfo_item("CPU architecture")
        # in case of mounting virtual filesystem of aarch64 kernel without linux32
        is_rootfs_v8 = (
            not re.match("^armv[0-9]+l$", machine) and
            (int('0' + next(iter(arch))) > 7 if arch else 0)
        )
        if re.match("^(aarch64|AARCH64)", machine) or is_rootfs_v8:
            self.features_map = {
                "NEON": "ASIMD", "HALF": "ASIMD", "VFPV4": "ASIMD"
            }
        else:
            self.features_map = dict(
                # ELF auxiliary vector and /proc/cpuinfo on Linux kernel(armv8 aarch32)
                # doesn't provide information about ASIMD, so we assume that ASIMD is supported
                # if the kernel reports any one of the following ARM8 features.
                ASIMD=("AES", "SHA1", "SHA2", "PMULL", "CRC32")
            )
