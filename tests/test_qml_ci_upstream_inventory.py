"""INC-QML-132: native source lanes collect the reviewed upstream merge matrix."""
from __future__ import annotations

from collections import defaultdict
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tests import qml_ci

ROOT = Path(__file__).resolve().parents[1]

# Bind the actual parametrized identities to the reviewed joint contracts and
# upstream controls. Collection may grow only with a matching inventory review.
EXPECTED = {
    "tests.test_upstream_100_publication": {
        *(f"test_req_qml022_ac06_inherited_source_profile_survives_last_parallel_pair[{operation}]"
          for operation in ("extract", "manual", "watch")),
        *(f"test_req_qml022_ac06_ordinary_raw_flags_reflect_parallel_links[{parallel}-{operation}]"
          for parallel in ("False", "True") for operation in ("extract", "manual", "watch")),
        *(f"test_req_qml022_ac06_bridge_rows_keep_profile_topology_and_generic_relations[{limit}-{direction}-{profile}]"
          for limit in ("bounded", "all") for direction in ("undirected", "directed")
          for profile in ("legacy", "source")),
    },
    "tests.test_upstream_100_extraction": {
        "test_req_qml010_ac01_ac02_ac03_req_qml022_ac02_ac06_case_only_roles_round_trip[type-first]",
        "test_req_qml010_ac01_ac02_ac03_req_qml022_ac02_ac06_case_only_roles_round_trip[function-first]",
        *(f"test_req_core005_ac01_ac02_jvm_changed_caller_retains_written_package_with_accepted_context[{state}-{language}-{caller}]"
          for state in ("valid", "missing", "null", "wrong-type", "oversize", "malformed", "not-type", "duplicate")
          for language in ("java", "kotlin") for caller in ("kotlin-caller", "java-caller")),
        *(f"test_req_core005_ac03_direct_producer_cache_export_preserve_exact_package[{package}-{language}]"
          for package in ("default", "named", "max") for language in ("java", "kotlin")),
        *(f"test_req_core005_ac02_malformed_or_oversize_source_package_cannot_become_default[{package}-{language}]"
          for package in ("malformed", "oversize", "recovered-header") for language in ("java", "kotlin")),
        *(f"test_req_core005_ac02_unique_same_name_provider_cannot_override_explicit_import[{state}-{caller}]"
          for state in ("wrong-package", "missing", "malformed") for caller in ("kotlin-caller", "java-caller")),
    },
    "tests.test_upstream_100_jvm_updates": {
        *(f"test_req_core005_ac01_ac03_jvm_changed_caller_publication_retains_recovers_repeats[{operation}]"
          for operation in ("manual", "watch")),
        "test_req_core005_ac02_unresolved_file_alias_identity_matches_full_partial_and_reorder",
    },
    "tests.test_4874_jvm_resolution": {
        "test_kotlin_import_of_java_class_targets_the_class_node",
        "test_java_import_and_inheritance_of_kotlin_class_target_the_class_node",
        "test_kotlin_member_call_reaches_the_java_method",
        "test_affected_reaches_dependents_in_both_languages",
        "test_existing_kotlin_subclass_of_java_base_is_unchanged",
        "test_java_to_kotlin_import_without_inheritance_targets_class",
        "test_external_java_import_does_not_bind_to_a_local_same_name_class",
        "test_same_simple_name_in_two_packages_uses_the_import_package",
        "test_jvm_call_does_not_bind_to_a_non_jvm_type",
    },
    "tests.test_4909_reference_binding_scale": {
        "test_reference_binding_scales_with_edges_not_imports",
    },
    "tests.test_case_only_decl_ids_4904": {
        *(f"test_type_and_function_differing_in_case_are_two_nodes[a.{extension}]"
          for extension in ("cpp", "js", "kt", "php", "rb", "swift", "ts")),
        "test_the_call_belongs_to_the_function_not_the_class",
        "test_same_spelling_across_kinds_stays_one_declaration",
        "test_registry_reuses_only_same_kind_or_same_spelling",
    },
    "tests.test_scala_extension_methods": {
        "test_extension_on_local_class_attaches_to_that_class",
        "test_extension_on_external_and_generic_types",
        "test_using_clause_is_not_the_receiver",
        "test_qualified_receiver_and_braced_body",
        "test_type_parameter_receiver_is_not_invented_as_a_type",
        "test_call_between_extension_methods_resolves",
        "test_extension_is_deterministic",
        "test_extension_in_another_file_attaches_to_the_real_class",
    },
    "tests.test_php_class_const_initializer_refs": {
        "test_const_value_scope_member_is_referenced",
        "test_property_default_scope_member_is_referenced",
        "test_parameter_default_scope_member_is_referenced",
        "test_promoted_constructor_parameter_default_is_referenced",
        "test_method_body_reference_still_works",
        "test_self_static_parent_scope_emits_no_spurious_edge",
        "test_qualified_scope_resolves_to_local_class",
    },
}


@pytest.fixture(scope="module")
def native_upstream_cases(tmp_path_factory):
    """Collect real selected modules offline without executing fixtures or installing extras."""
    selected = qml_ci.selected_tests(ROOT)
    reviewed = {module.replace(".", "/") + ".py" for module in EXPECTED}
    assert reviewed <= {Path(path).as_posix() for path in selected}
    # Prefix selection also owns future merge-specific modules. An added module
    # must update this reviewed matrix rather than silently escape its guard.
    joint = {Path(path).as_posix() for path in selected
             if Path(path).name.startswith("test_upstream_100_")}
    assert joint == {path for path in reviewed if Path(path).name.startswith("test_upstream_100_")}
    output = tmp_path_factory.mktemp("native100_collection") / "cases.json"
    collector = """import json
from pathlib import Path
import sys
import pytest

class Collector:
    def pytest_collection_finish(self, session):
        cases = [(item.module.__name__, item.name) for item in session.items]
        Path(sys.argv[1]).write_text(json.dumps(cases), encoding="utf-8")

raise SystemExit(pytest.main([*sys.argv[2:], "--collect-only", "-q", "-p", "no:cacheprovider"],
                             plugins=[Collector()]))
"""
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", collector, str(output), *sorted(reviewed)],
        cwd=ROOT, env=dict(os.environ, PYTEST_ADDOPTS="", PYTHONUTF8="1"),
        capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)[-4000:]
    return json.loads(output.read_text(encoding="utf-8"))


def test_req_qml018_ac06_native_upstream_inventory_matches_actual_collected_cases(native_upstream_cases):
    """The production native selection retains every reviewed case exactly once."""
    actual = defaultdict(set)
    assert len({tuple(case) for case in native_upstream_cases}) == len(native_upstream_cases)
    for module, name in native_upstream_cases:
        actual[module].add(name)
    assert dict(actual) == EXPECTED


def test_req_qml018_ac06_artifact_inventory_excludes_native_source_contracts():
    """The Ubuntu artifact profile keeps its isolated optional/core wheel boundary."""
    assert qml_ci.selected_tests(ROOT, artifact_only=True) == ["tests/test_qml_wheel_artifact.py"]
