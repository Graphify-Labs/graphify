# Acceptance traceability

Current criterion IDs use `REQ-QML-`; completion increments use `INC-QML-`.
[Legacy aliases](../docs/qt-qml/IDENTIFIERS.md) retain earlier evidence identity.
Recorded test identities retain their historical evidence; current renamed viewer
tests are mapped to their actual functions below. Source annotations keep their IDs.

The current catalog contains twenty-one requirements and eighty-five stable
acceptance criteria. REQ-QML-018 has seven criteria, including the separate AC07
header-dispatch contract; REQ-QML-019/020/021 retain four/three/three criteria.
INC-QML-00–07 hosted proof describes its original seventeen-requirement,
sixty-eight-criterion profile. Subsequent evidence does not retroactively broaden
those historical results.

INC-QML-11/15/08a/b/c and INC-QML-28–38 have current local source, update, consumer
and reviewed installed-wheel evidence. All seven REQ-QML-018 criteria are locally
verified for the bounded Windows x64/Python 3.12 profile. Individual assignments
and the [final local matrix](#final-adoption-delivery) distinguish passing cases
from wider platform, native interaction, live-service and runtime limitations.
The recorded full source run has 59 baseline failures and 178 skips, with no added
failure identities; full typing remains a failed baseline gate. The later
[Windows dependency follow-up](../docs/qt-qml/VALIDATION.md#windows-shell-and-optional-dependency-follow-up--2026-10-04)
clears 40 of those 59 in a selective rerun, retains 19, and exposes two previously
skipped hook portability assertions. It does not replace full-suite evidence.
Neither aggregate test totals nor skipped cases establish acceptance.

The separate [shared compatibility checkpoint](#shared-compatibility-verification)
records `REQ-CORE-` behavior and the all-extras environment. A post-restart full
Windows/Linux run is pending; the original full-suite evidence above remains
historical and is not replaced by focused passing selections.

The chronological records below preserve checkpoint evidence. Their older pending
statements, epochs and test totals describe the recorded revisions. Current status
and proof are in the final matrix and [validation](../docs/qt-qml/VALIDATION.md#final-adoption-delivery).
See [implementation limits](../docs/qt-qml/IMPLEMENTATION.md#final-adoption-delivery),
[export contracts](../docs/qt-qml/EXPORT_MATRIX.md) and
[platform matrix](../docs/qt-qml/PLATFORM_MATRIX.md).

## Shared compatibility verification

The Windows x64/Python 3.12 checkpoint installs all extras from the unchanged
lock with `uv sync --all-extras --frozen`; `uv pip check` reports 197 compatible
packages. Tree-sitter remains 0.25.2, HCL 1.2.0 and language-pack 0.11.0.
The [compatibility plan](../docs/COMPATIBILITY.md) records profile setup, exact
remaining system procedure, ownership, size ceilings and consumer limitations.

| Acceptance ID | Exact automated assignment | Checkpoint evidence and gaps |
| --- | --- | --- |
| REQ-CORE-001-AC01 | `tests/test_codex_hook_execution.py::test_req_core001_ac01_codex_hook_dispatches_spaced_native_launcher`; `tests/test_install.py::test_codex_hook_command_is_a_real_cli_subcommand` | Exact Cmd and Windows PowerShell 5.1 argument transports pass with a real selected launcher, failing PATH decoy and unsafe control; installed-artifact/full-source proof in progress |
| REQ-CORE-001-AC02 | `tests/test_install.py::test_hermes_skill_destination_posix_uses_home`; `tests/test_install_references.py::test_gemini_install_references_all_resolve`; `tests/test_install_roundtrip.py::test_skill_roundtrip_at_real_destination` | Exact destination and Linux/Windows contract profiles pass locally; simulated platform selection does not prove another kernel |
| REQ-CORE-001-AC03 | `tests/test_skill_auto_refresh.py::test_every_stale_platform_is_refreshed_not_only_the_detected_one`; `tests/test_skill_auto_refresh.py::test_a_stale_gemini_skill_gets_the_warning_too` | Windows-adapted bytes and retained ambiguous shared copy pass; shared ownership isolation remains unresolved upstream |
| REQ-CORE-001-AC04 | `tests/test_uninstall_scope.py::test_bare_call_still_removes_global`; `tests/test_uninstall_scope.py::test_remove_user_skill_opt_in_with_project_dir` | Linux/Windows scope profiles and protected shared-dir retention pass; no new uninstall policy |
| REQ-CORE-001-AC05 | `tests/test_codex_hook_execution.py::test_req_core001_ac05_literal_expansion_characters_retain_launcher_identity`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_missing_launcher_fails_without_path_fallback`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_selected_process_failure_preserves_nonzero_exit`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_reinstall_and_uninstall_preserve_unrelated_hooks`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_unsupported_shell_rejects_before_settings_access`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_shell_inspection_failure_retains_settings_and_backup`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_command_length_boundary_retains_literal_identity` | Native Cmd/Windows PowerShell 5.1 executable identity, failure/retention and rejected serialization boundaries characterized; full-source and installed-artifact execution in progress. Synthetic length cases establish admission/retention, not a real long-path launch. Actual Codex event delivery and other PowerShell versions remain separate system gaps. |
| REQ-CORE-002-AC01 | `tests/test_filesystem_profiles.py::test_req_core_002_ac01_detect_rejects_nonregular_stat_modes`; `tests/test_filesystem_profiles.py::test_req_core_002_ac01_stat_failures_are_unreadable`; original real fixtures in `tests/test_non_regular_files.py` | Native admission/error seams pass; actual FIFO/socket/device and privileged symlink fixtures remain capability exclusions, not passing real-object evidence |
| REQ-CORE-002-AC02 | `tests/test_filesystem_profiles.py::test_req_core_002_ac02_unavailable_cwd_rejects_before_artifacts`; `tests/test_filesystem_profiles.py::test_req_core_002_ac02_repo_root_recovers_cwd_and_publishes_graph`; `tests/test_watch.py::test_rebuild_code_deleted_cwd_without_repo_root_returns_false`; `tests/test_watch.py::test_rebuild_code_deleted_cwd_uses_graphify_repo_root` | Native simulated lookup-failure plus real chdir/persistence pass; actual removed-CWD POSIX fixtures pending |
| REQ-CORE-002-AC03 | `tests/test_filesystem_profiles.py::test_req_core_002_ac03_unavailable_cwd_reports_root_reason` | Missing-root/chdir-denied assertions failed before correction; all three safe diagnostic categories pass after correction |
| REQ-CORE-003-AC01 | `tests/test_terraform_modules.py::test_same_named_directories_and_cross_file_references_stay_separate` | Both LF/CRLF cases pass exact four identities/references and exclude cross-directory targets |
| REQ-CORE-003-AC02 | `tests/test_terraform_modules.py::test_same_named_directories_and_cross_file_references_stay_separate`; `tests/test_terraform_modules.py::test_raw_extractor_scopes_ids_by_full_directory` | Production extraction, directed build and JSON reload pass portable paths, locations and scope; Terraform production unchanged |

Focused commands and results at the checkpoint:

- Final INC-CORE-05 consumer correction: `PYTHONUTF8=1 python -X utf8 -m pytest tests/test_codex_hook_execution.py -q --tb=short -p no:cacheprovider` passes 19 cases, with no skips and one existing Hypothesis discovery warning. Both actual Windows shells exercise the persisted command. Installer/settings-merge/hook characterization passes 143 cases with three existing profile skips; these selections overlap and are not added to the full-suite count.
- `pytest tests/test_install.py tests/test_install_references.py tests/test_install_roundtrip.py tests/test_skill_auto_refresh.py tests/test_uninstall_scope.py tests/test_codex_hook_execution.py -q`: 243 passed, five native symlink skips. Strengthened exact-launcher/subcommand follow-up: two passed.
- `pytest tests/test_hooks.py tests/test_skillgen_input_path_injection.py -q`: 143 passed, eight pre-existing profile skips. The final affected selection plus shell-identity helpers: 37 passed, no skips. All 20 hostile-path cases include reachable unsafe controls.
- `pytest tests/test_watch.py tests/test_non_regular_files.py tests/test_filesystem_profiles.py -q`: 198 passed, eleven profile/capability skips, one existing Hypothesis warning. Seven formerly failing impossible Windows fixtures now remain explicit system gaps; sixteen new portable cases pass.
- `pytest tests/test_terraform.py tests/test_terraform_modules.py tests/test_extractors_registry.py::test_terraform_migrated -q`: 42 passed, one unavailable symlink skip, one existing Hypothesis warning.
- `ruff check .`: passed. `python -m tools.skillgen --check`: all 134 artifacts match. Lockfile unchanged. Full source/platform and refreshed installed-wheel evidence remains pending after the WSL restart.

These selections overlap and are not added into a full-suite total. Real filesystem
capability assertions, native hook consumer execution and live-service tests remain
separate from contract profiles and fake-provider boundaries. Full typing is a
separate gate and is not established by Ruff or selected tests.

## Individual acceptance assignments

The [follow-up audit](../docs/qt-qml/FOLLOWUP_AUDIT.md) supplies counterexamples for
REQ-QML-008-AC01/AC03, REQ-QML-016-AC01–AC04 and REQ-QML-017-AC02/AC03/AC04. The table's historical
passes do not cover those cases. Current INC-QML-17–20 correction evidence appears
below; affected criteria retain explicit expanded-profile gaps.
Exact opt-in probes and corrective increments appear in
[scope corrections](#follow-up-audit-scope-corrections).

Exact test references below identify executed cases. Documentation, privacy and
hosted integration reviews are explicit review evidence rather than invented unit
tests. Later revisions reverify affected evidence; preserve these identifiers.

| Acceptance ID | Actual evidence / assigned open case | Planned completion increment | Status |
| --- | --- | --- | --- |
| REQ-QML-001-AC01 | `tests/test_qml_wheel_artifact.py::test_qml001_ac01_built_wheel_contains_adapter_and_optional_extra_metadata`; `tests/test_qml_wheel_artifact.py::test_qml001_ac01_ac03_built_artifact_production_import_and_parser_boundary` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-001-AC02 | `tests/test_qml_syntax_profile.py::test_qml001_ac02_handchecked_profile_uses_production_extractor_and_original_spans`; `tests/test_qml_syntax_profile.py::test_qml001_ac02_profile_runs_offline_in_fresh_production_process_without_corpus_execution` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-001-AC03 | `tests/test_qml_failures.py::test_qml001_ac03_missing_optional_import_is_safe_and_does_not_break_python`; `tests/test_qml_failures.py::test_qml001_ac03_incompatible_parser_load_is_bounded_failure` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-001-AC04 | `tests/test_qml_declarations.py::test_qml001_ac04_empty_source_is_distinguishable_from_parse_failure`; `tests/test_qml_declarations.py::test_qml012_ac01_malformed_or_partial_parse_has_no_authoritative_nodes`; `tests/test_qml_failures.py::test_qml001_ac04_unsupported_annotated_root_is_not_file_only_success` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-002-AC01 | `tests/test_qt_config_incremental.py::test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider; tests/test_qml_identity.py::test_qml01_ui_suffix_names_component_without_losing_filename_identity` | INC-QML-06 | Verified static source profile |
| REQ-QML-002-AC02 | `tests/test_qt_metadata_admission.py::test_cmake_exact_name_does_not_reclassify_arbitrary_text; tests/test_qml_integration.py::test_qml002_ac02_named_qmldir_dispatch_directory_and_single_file_root` | INC-QML-06 | Verified static source profile |
| REQ-QML-002-AC03 | `tests/test_qt_metadata_admission.py::test_qt_metadata_discovery_obeys_existing_ignore_policy; tests/test_qt_resource_resolution.py::test_qrc_host_reads_entities_traversal_and_malformed_xml_rejected` | INC-QML-06 | Verified static source profile |
| REQ-QML-002-AC04 | `tests/test_qml_identity.py::test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts; tests/test_qt_config_incremental.py::test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider` | INC-QML-06 | Verified static source profile |
| REQ-QML-003-AC01 | `tests/test_qml_declarations.py::test_qml003_ac01_exact_declarations_ownership_and_raw_types`; `tests/test_qml_declarations.py::test_qml003_ac01_unicode_crlf_spans_and_original_names`; `tests/test_qml_syntax_profile.py::test_qml003_ac01_property_binding_and_array_objects_keep_exact_owners` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-003-AC02 | `tests/test_qml_identity.py::test_qml003_ac02_duplicate_basename_uses_full_relative_path`; `tests/test_qml_identity.py::test_qml003_ac02_inline_component_equal_ids_and_members_have_separate_owners`; `tests/test_qml_graph.py::test_qml003_ac02_same_stem_cpp_js_and_qml_do_not_merge`; template barrier cases in test_qml_syntax_profile.py | INC-QML-01 | Verified (declared profile) |
| REQ-QML-003-AC03 | `tests/test_qml_declarations.py::test_qml003_ac03_comments_literals_groups_and_js_inner_functions_are_not_objects` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-003-AC04 | `tests/test_qml_identity.py::test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts`; `tests/test_qml_identity.py::test_qml003_ac04_comment_insert_changes_spans_but_not_named_identity`; `tests/test_qml_integration.py::test_qml010_ac01_real_process_pool_and_warm_order_match_sequential` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-004-AC01 | `tests/test_qml_resolution.py::test_aliased_directory_and_uri_imports_do_not_cross_bind`; `tests/test_qml_resolution.py::test_version_availability_and_latest_compatible_export` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-004-AC02 | `tests/test_qml_resolution.py::test_aliased_directory_and_uri_imports_do_not_cross_bind`; `tests/test_qml_resolution.py::test_versioned_layout_and_missing_version_evidence` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-004-AC03 | `tests/test_qml_resolution.py::test_competing_providers_and_missing_modules_have_no_target_edges` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-004-AC04 | `tests/test_qml_resolution.py::test_declared_roots_and_remote_import_never_expand_corpus`; `tests/test_qml_resolution.py::test_directory_and_script_projection_and_ignored_disk_provider` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-005-AC01 | `tests/test_qml_scope.py::test_component_ids_do_not_leak_between_files_or_inline_components` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-005-AC02 | `tests/test_qml_scope.py::test_inline_shadow_and_inherited_members_are_distinct_roles`; `tests/test_qml_scope.py::test_singleton_pragma_and_qualified_access` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-005-AC03 | `tests/test_qml_scope.py::test_internal_external_dynamic_and_lexical_members_stay_unresolved` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-005-AC04 | `tests/test_qml_resolution.py::test_module_script_exports_have_separate_lookup_roles` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-006-AC01 | `tests/test_qml_expressions.py::test_binding_reads_and_nested_qualified_aliases` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-006-AC02 | `tests/test_qml_expressions.py::test_alias_cycles_missing_and_ambiguous_targets_never_guess`; `tests/test_qml_expressions.py::test_component_and_object_scope_do_not_bind_hidden_identifiers` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-006-AC03 | `tests/test_qml_expressions.py::test_dynamic_reads_and_executable_source_are_only_analyzed` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-006-AC04 | `tests/test_qml_expressions.py::test_repeated_sites_survive_actual_directed_build_and_json`; `tests/test_qml_integration.py::test_qml010_ac02_default_undirected_export_reload_keeps_qml_direction` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-007-AC01 | `tests/test_qml_handlers.py::test_parameters_block_bindings_nested_functions_and_computed_calls`; `tests/test_qml_handlers.py::test_inherited_and_alias_target_signal_parameters_shadow_properties` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-007-AC02 | `tests/test_qml_scripts.py::test_literal_imported_helpers_and_library_do_not_inherit_document_ids`; `tests/test_qml_scripts.py::test_mjs_explicit_exports_aliases_and_private_functions`; `tests/test_qml_scripts.py::test_accepted_script_dependencies_support_classic_and_esm_imports`; `tests/test_qml_scripts.py::test_script_overlay_retains_original_shared_js_nodes_and_never_executes` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-007-AC03 | `tests/test_qml_handlers.py::test_declared_and_property_change_handlers_are_subscriptions`; `tests/test_qml_handlers.py::test_connections_target_and_dynamic_target_stay_distinct`; `tests/test_qml_adversarial.py::test_mixed_legacy_connections_handlers_do_not_activate_ignored_function_handlers` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-007-AC04 | `tests/test_qml_scripts.py::test_generic_js_calls_cannot_bind_to_qml_owned_expression_sites`; `tests/test_qml_scripts.py::test_script_overlay_does_not_read_unaccepted_imports_or_network` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-008-AC01 | `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints` | INC-QML-05 | Locally verified bounded alias registration correction; adoption gaps retained |
| REQ-QML-008-AC02 | `tests/test_qt_cpp_exposure.py::test_header_implementation_members_reuse_accepted_canonical_ids`; `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints`; `tests/test_qt_cpp_definition_ownership.py::test_req_qml008_ac02_definition_provenance_keeps_emission_owned_through_aggregate`; normalization, conflicting callable/body, missing completeness, external/local class, generic identity and original-byte controls in that module; `tests/test_qt_cpp_owner_upgrade.py::test_qml008_ac02_policy_three_reparses_unchanged_native_ownership` (update/extract); [current constructor/source-containment assignments](#constructor-and-source-containment-corrections) | INC-QML-05; INC-QML-10/12/13 corrections | Locally verified bounded ownership; qualified ID correction has separate INC-QML-21 evidence below |
| REQ-QML-008-AC03 | `tests/test_qt_native_project_integration.py::test_cpp_source_in_two_distinct_build_contexts_has_no_arbitrary_native_provider; tests/test_qt_qml_integration.py::test_ambiguous_overload_and_version_revised_member_are_explicit` | INC-QML-05 | Locally verified bounded alias rejection; broader adoption/overload gaps retained |
| REQ-QML-008-AC04 | `tests/test_qt_cpp_syntax.py::test_unicode_crlf_macro_spans_are_original_bytes; tests/test_qt_cpp_syntax.py::test_comments_strings_raw_literals_and_preprocessor_definitions_are_inert` | INC-QML-05 | Verified static source profile |
| REQ-QML-009-AC01 | `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints; tests/test_qt_resource_resolution.py::test_public_qt6_cmake_and_qmake_fixtures_describe_identical_membership` | INC-QML-05 | Verified static source profile |
| REQ-QML-009-AC02 | `tests/test_qml_types_metadata.py::test_qmltypes_members_flags_exports_original_byte_provenance; tests/test_qml_types_metadata.py::test_qmltypes_cpp_member_conflict_preserves_authoritative_source` | INC-QML-05 | Verified static source profile |
| REQ-QML-009-AC03 | `tests/test_qt_project_admission.py::test_qml009_ac03_public_metadata_qrc_load_build_export_reload; tests/test_qt_resource_resolution.py::test_qrc_host_reads_entities_traversal_and_malformed_xml_rejected` | INC-QML-05 | Verified static source profile |
| REQ-QML-009-AC04 | `tests/test_qt_project_metadata.py::test_cmake_conditional_and_expanded_metadata_is_not_authoritative; tests/test_qt_project_metadata.py::test_qmake_conditions_expansion_functions_never_produce_guessed_context` | INC-QML-05 | Verified static source profile |
| REQ-QML-010-AC01 | `tests/test_qt_worker_cache_integrity.py::test_qml010_ac01_actual_workers_preserve_configured_roots_script_and_native_facts`; `tests/test_qml_identity.py::test_qml010_ac01_filename_normalization_collisions_keep_distinct_ids`; `tests/test_qml_identity.py::test_qml003_ac02_unicode_normalization_colliding_members_remain_distinct`; `tests/test_qml_integration.py::test_qml010_ac01_real_process_pool_and_warm_order_match_sequential` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-010-AC02 | `tests/test_qt_qml_export_consumers.py::test_json_repeated_native_mechanisms_remain_distinct_and_directional`; `tests/test_qt_qml_export_consumers.py::test_native_path_reports_qml_call_site_and_cpp_declaration_without_reversing_flow`; `tests/test_qt_graph_persistence.py` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-010-AC03 | `tests/test_qt_qml_export_consumers.py::test_json_repeated_native_mechanisms_remain_distinct_and_directional`; `tests/test_qml_expressions.py::test_repeated_sites_survive_actual_directed_build_and_json`; `tests/test_qt_export_matrix.py::test_cypher_keeps_parallel_mechanisms_and_escapes_literal_data` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-010-AC04 | `tests/test_qt_affected_definitions.py::test_qml016_ac04_signal_change_reports_canonical_out_of_line_function_owner`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls`; `tests/test_qt_graph_persistence.py`; `tests/test_build.py::test_build_merge_sln_stub_does_not_replace_referenced_csproj`; `tests/test_build.py::test_build_merge_project_reference_stub_does_not_replace_referenced_project`; `tests/test_build.py::test_merge_raw_extraction_cross_file_stub_parity` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-011-AC01 | `tests/test_qt_final_incremental_parity.py::test_qml011_ac01_real_normal_qml_edit_matches_cold_warm_manual_and_watch`; `tests/test_qt_metadata_incremental.py::test_native_cpp_provider_only_edit_refreshes_unchanged_qml_and_warm_overlay` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-011-AC02 | `tests/test_qt_metadata_incremental.py::test_build_provider_only_mutations_equal_clean_accepted_corpus; tests/test_qt_metadata_incremental.py::test_resource_only_mutations_refresh_unchanged_cpp_loaders; tests/test_qt_config_incremental.py::test_qml011_ac02_last_qt_source_deletion_cleans_facts_and_commits_nonqt_state` | INC-QML-06 | Verified static source profile |
| REQ-QML-011-AC03 | `tests/test_qt_config_incremental.py::test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider; tests/test_qt_config_incremental.py::test_qml011_ac03_package_version_change_reanalyzes_unchanged_corpus` | INC-QML-06 | Verified static source profile |
| REQ-QML-011-AC04 | `tests/test_qt_final_incremental_parity.py::test_qml011_ac04_real_no_change_updates_preserve_every_fact_and_unrelated_python`; `tests/test_qt_metadata_incremental.py::test_build_provider_only_mutations_equal_clean_accepted_corpus`; `tests/test_qt_metadata_incremental.py::test_resource_only_mutations_refresh_unchanged_cpp_loaders` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-012-AC01 | `tests/test_qml_failures.py::test_qml001_ac03_missing_optional_import_is_safe_and_does_not_break_python`; `tests/test_qml_failures.py::test_qml012_ac01_native_parse_exception_is_explicit_safe_failure`; `tests/test_qml_resolver_safety.py::test_native_join_failure_is_guarded_and_successful_retry_is_clean` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-012-AC02 | `tests/test_qt_worker_cache_integrity.py::test_qml012_ac02_failed_native_parser_keeps_prior_real_ast_cache_and_products`; `tests/test_qt_config_incremental.py::test_qml012_ac02_malformed_new_source_preserves_graph_manifest_and_stamp`; `tests/test_qt_metadata_incremental.py::test_failed_metadata_update_preserves_prior_graph_manifest_and_report` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-012-AC03 | `tests/test_qt_config_incremental.py::test_qml011_ac02_last_qt_source_deletion_cleans_facts_and_commits_nonqt_state`; `tests/test_qml_watch_persistence.py::test_watch_qml_failure_preserves_completed_products_with_force`; `tests/test_qml_cli_persistence.py` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-012-AC04 | `tests/test_qml_failures.py::test_qml012_ac04_deep_source_terminates_at_supported_bound`; `tests/test_qml_failures.py::test_qml012_ac04_explicit_root_rejection_does_not_expose_absolute_paths`; `tests/test_qt_resource_resolution.py::test_qrc_host_reads_entities_traversal_and_malformed_xml_rejected`; `tests/test_qt_qml_search.py::test_deep_malformed_literal_transport_cannot_crash_production_search` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-013-AC01 | `tests/test_qt_query_consumers.py::test_cli_query_explain_and_path_use_source_scoped_nodes`; `tests/test_qt_qml_export_consumers.py::test_native_path_reports_qml_call_site_and_cpp_declaration_without_reversing_flow`; `tests/test_qt_mcp_consumers.py::test_mcp_exact_id_path_matches_cli_and_retains_source_evidence` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-013-AC02 | `tests/test_qt_affected_consumers.py::test_property_change_reports_binding_and_owning_component`; `tests/test_qt_affected_definitions.py::test_qml016_ac04_signal_change_reports_canonical_out_of_line_function_owner`; `tests/test_qt_affected_consumers.py::test_future_metadata_or_foreign_file_ownership_is_not_dependency_evidence` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-013-AC03 | `tests/test_qt_qml_export_consumers.py`; `tests/test_qt_export_matrix.py`; `tests/test_qt_graph_html_payload.py`; `tests/test_qt_html_consumers.py`; `tests/test_qt_source_coverage_report.py`; format-specific omissions and unexecuted live database behavior: [EXPORT_MATRIX](../docs/qt-qml/EXPORT_MATRIX.md) | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-013-AC04 | `tests/test_qt_mcp_consumers.py`; `tests/test_qt_mcp_stdio.py`; `tests/test_qt_qml_search.py` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-014-AC01 | `tests/test_qml_wheel_artifact.py`; `tests/test_qml_platform_matrix.py`; `tests/qml_installed_smoke.py`; twelve exact-head optional/core wheel jobs: [PLATFORM_MATRIX](../docs/qt-qml/PLATFORM_MATRIX.md) | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-014-AC02 | `tests/test_qml_identity.py::test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts`; `tests/test_qt_cpp_syntax.py::test_unicode_crlf_macro_spans_are_original_bytes`; `tests/test_qml_wheel_artifact.py::test_qml001_ac01_ac03_built_artifact_production_import_and_parser_boundary` | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-014-AC03 | `tests/test_extract.py`; `tests/test_cache.py`; `tests/test_serve.py`; `tests/test_export.py`; `tests/test_affected_cli.py`; `tests/test_callflow_html.py`; affected baseline full suites in four hosted Ubuntu Python lanes; local optional skips and Windows baseline defects remain in VALIDATION.md | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-014-AC04 | Executed skip/baseline/typing accounting in [VALIDATION](../docs/qt-qml/VALIDATION.md); optional MCP executed through actual HTTP/stdio; absent SVG is an explicit omission | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-015-AC01 | Requirement/68-criterion/link/status review and reviewable stacked PRs; [IMPLEMENTATION](../docs/qt-qml/IMPLEMENTATION.md), [PLAN](../docs/qt-qml/PLAN.md) | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-015-AC02 | `tests/test_qml_skillgen_guidance.py`; `tests/test_skillgen.py`; five generator validators run separately; all 134 generated artifacts and expected outputs regenerated | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-015-AC03 | Verified upstream v8/base/head and earlier upstream proposal read-only; preserved grammar attribution; exact PR head/base/tested merge and workflows recorded in [VALIDATION](../docs/qt-qml/VALIDATION.md) | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-015-AC04 | Executed public privacy/reference/footprint review; all 68 criteria accounted for with explicit static/runtime/platform/export boundaries; [README](../docs/qt-qml/README.md), [EXPORT_MATRIX](../docs/qt-qml/EXPORT_MATRIX.md), [PLATFORM_MATRIX](../docs/qt-qml/PLATFORM_MATRIX.md) | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-016-AC01 | `tests/test_qt_cpp_syntax.py::test_access_sections_keep_original_roles_offsets`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls`; `tests/test_qt_signals_slots.py::test_macro_sections_private_meta_slots_and_comments`; `tests/test_qt_cpp_definition_ownership.py::test_req_qml016_ac01_forward_declaration_does_not_compete_with_complete_definition` | INC-QML-04b; INC-QML-10 correction | Partial; alias correction locally verified; inherited/qualified identity gaps INC-QML-11/21 |
| REQ-QML-016-AC02 | `tests/test_qt_signals_slots.py::test_overloads_need_selector_and_dynamic_sender_stays_unresolved`; `tests/test_qt_events_boundaries.py::test_functor_function_and_connection_handle_disconnect`; `tests/test_qt_events_boundaries.py::test_explicit_cast_signal_to_signal_and_condition_flags`; `tests/test_qt_events_boundaries.py::test_private_typed_pointer_and_incompatible_receiver_are_rejected`; [alias counterexamples](#follow-up-audit-scope-corrections) | INC-QML-04b; INC-QML-19 correction | Locally verified bounded aliases; generic overload gap INC-QML-15 retained |
| REQ-QML-016-AC03 | `tests/test_qt_events_boundaries.py::test_explicit_cast_signal_to_signal_and_condition_flags`; `tests/test_qt_events_boundaries.py::test_computed_signal_receiver_and_custom_connect_are_not_qt_targets`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls`; [alias counterexamples](#follow-up-audit-scope-corrections) | INC-QML-04b; INC-QML-19 correction | Locally verified bounded alias/conditional rejection; unsupported forms retained |
| REQ-QML-016-AC04 | `tests/test_qt_event_incremental_consumers.py::test_qml016_ac04_event_mutation_and_removal_match_clean_rebuild_without_delivery_calls`; `tests/test_qt_html_consumers.py::test_signal_emission_is_not_rendered_as_a_caller_in_the_call_table`; `tests/test_qt_affected_definitions.py`; `tests/test_qt_mcp_consumers.py::test_qml016_ac04_http_metadata_search_keeps_connection_reference_semantics`; `tests/test_qt_worker_cache_integrity.py`; `tests/test_qt_cpp_owner_upgrade.py::test_qml016_ac04_failed_owner_upgrade_retains_prior_graph_stamp_and_manifest` (force off/on); persisted JSON and aggregate ownership in `tests/test_qt_cpp_definition_ownership.py` | INC-QML-07; INC-QML-10 correction | Partial; alias lifecycle/artifact evidence passes; inherited/qualified identity gaps retained |
| REQ-QML-017-AC01 | `tests/test_qt_project_admission.py::test_qml017_ac01_literal_module_load_reaches_declared_component_and_property; tests/test_qt_project_admission.py::test_qml009_ac03_public_metadata_qrc_load_build_export_reload` | INC-QML-05 | Locally verified bounded literal loader correction; omitted API families excluded |
| REQ-QML-017-AC02 | `tests/test_qml_cpp_access.py::test_view_root_and_literal_object_name_property_access`; `tests/test_qt_access_providers.py::test_qqmlproperty_read_write_preserves_property_handle`; `tests/test_qt_project_admission.py::test_qml017_ac01_literal_module_load_reaches_declared_component_and_property`; `tests/test_qt_cpp_definition_ownership.py::test_req_qml017_ac02_namespace_definition_owns_source_backed_qml_access`; [receiver counterexamples](#follow-up-audit-scope-corrections) | INC-QML-05; INC-QML-10/17 corrections | Partial; receiver correction passes; static reflection correction has separate INC-QML-22 evidence below |
| REQ-QML-017-AC03 | `tests/test_qt_access_providers.py`; `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints`; `tests/test_qt_native_project_integration.py`; [engine counterexample](#follow-up-audit-scope-corrections) | INC-QML-05; INC-QML-18 correction | Locally verified exact declaration/provider and component-engine profile; factory/member gap retained |
| REQ-QML-017-AC04 | `tests/test_qt_final_incremental_parity.py::test_qml017_ac04_qml_member_edit_refreshes_unchanged_reverse_cpp_access`; `tests/test_qml_cpp_access.py::test_duplicate_object_names_do_not_select_first_child`; `tests/test_qt_access_providers.py::test_duplicate_context_provider_and_local_shadow_do_not_choose`; `tests/test_qt_metadata_incremental.py`; `tests/test_qt_qml_export_consumers.py`; `tests/test_qt_mcp_stdio.py`; persisted export ownership in `tests/test_qt_cpp_definition_ownership.py::test_req_qml017_ac02_namespace_definition_owns_source_backed_qml_access`; [audit counterexamples](#follow-up-audit-scope-corrections) | INC-QML-07; INC-QML-10/17/18 corrections | Partial; bounded receiver/provider/loader lifecycle passes; INC-QML-21/22 have separate evidence below; wider system gaps remain |

## Native ownership correction and remaining gaps

The baseline follow-up audit A13 failed REQ-QML-008-AC01/AC03 and REQ-QML-016-AC01/AC04
for lexical aliases despite the earlier bounded passes in the individual table.
These statuses are partial/failed for the new cases. INC-QML-19 owns their
registration/emission/connection correction; INC-QML-11 remains inherited lookup.

INC-QML-10's bounded source-ownership correction is locally verified through the
production facade, graph assembly, JSON publication/reload, aggregate HTML and
real CLI upgrade/retention paths. The final focused ownership/context/upgrade
selection passes 88 cases in 7.38 seconds. The reviewed final-wheel Qt/QML, C++,
HTML and export selection passes 954 cases with seven documented skips. Exact
commands, artifact identity and red/green evidence belong to
[validation](../docs/qt-qml/VALIDATION.md#inc-qml-10-native-source-ownership).
These results do not establish browser appearance or new hosted/platform evidence.

Accepted unchanged-header contexts have separate production regressions in
`tests/test_qt_cpp_context_ownership.py::test_req_qml008_ac02_borrowed_complete_header_is_not_counted_as_two_definitions`
and `tests/test_qt_cpp_context_ownership.py::test_req_qml016_ac01_context_pipeline_preserves_owned_emission_through_json_reload`.
They map REQ-QML-008-AC02 and REQ-QML-016-AC01/AC04 to actual collector and
pipeline/join/build/publication/reload ownership, canonical IDs and unchanged
borrowed dictionaries. Genuine distinct-body and false/missing completeness
controls in the same module retain unproved endpoints; equivalent relative,
Windows-separator and absolute path spellings retain one body identity. These
cases first failed before the borrowed source/span transport correction and pass
within the final focused selection.

INC-QML-11 now corrects grandparent inherited-signal endpoint lookup under
REQ-QML-016-AC01/AC04 with the exact source/update evidence below. Earlier
immediate-base-only evidence is superseded for this bounded lookup profile. INC-QML-12/13 now have bounded source
implementation and regression evidence below. Missing/unaccepted class bodies,
collapsed overloads and dynamic targets retain explicit unavailable ownership.
A proven enclosing callable or accepted source file may contain the occurrence
without establishing its native class, QObject role or semantic target. These
corrections do not use containment as proof of a missing class or runtime call.

## Constructor and source-containment corrections

INC-QML-12 owns generic constructor declaration/definition proof and canonical
parent correction. INC-QML-13 owns native source-site/file containment, upgrade
invalidation and truthful community counts. Final reviewed policy-5/schema-7
wheel identity, complete suite and installed public source-file proof are in
[validation](../docs/qt-qml/VALIDATION.md#inc-qml-1213-current-source-and-view-evidence).
The earlier 1029-pass artifact used policy 4 and does not verify the final
source-file change. Each row retains its original criterion identity.

| Affected criterion | Exact production regression evidence | Boundary and current state |
| --- | --- | --- |
| REQ-QML-008-AC02 | `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_constructor_prototypes_are_callable_methods`; `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_constructor_definition_retains_id_and_exact_accepted_owner`; `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_constructor_join_rejects_foreign_or_corrupt_accepted_proof`; `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_corrupted_owner_cannot_relabel_another_actual_constructor`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_plain_member_uses_exact_callable_without_native_class_claim`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_local_class_links_to_enclosing_callable_without_type_authority`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_source_fallback_rejects_unproved_or_noncallable_context`; `tests/test_qt_source_file_containment.py::test_req_qml008_ac02_unknown_native_owner_keeps_actual_file_context_after_reload`; `tests/test_qt_source_file_containment.py::test_req_qml008_ac02_file_context_requires_unique_actual_file_role` | Locally verified bounded ownership; qualified ID correction has separate INC-QML-21 evidence below |
| REQ-QML-010-AC02/AC04 | `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_generic_constructor_facts_keep_original_bom_crlf_unicode_spans`; `tests/test_qt_constructor_ownership.py::test_req_qml008_ac02_constructor_spans_use_original_bom_crlf_unicode_bytes`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_source_link_survives_build_json_and_aggregate`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_direct_collector_borrows_exact_callable_without_mutating_context`; file containment/reload and role-rejection cases above | Original bytes, canonical IDs, EXTRACTED containment direction, immutable borrowed dictionaries and unresolved native status remain separate from inferred target resolution. Current artifact/reload proof passes. |
| REQ-QML-011-AC03 | `tests/test_qt_source_links_upgrade.py::test_req_qml011_ac03_source_links_upgrade_reparses_unchanged_cpp` (extract/update; prior policy/schema 3/6 and 4/7) | Real CLI reparses unchanged accepted C++ at the same package version, retires incompatible AST entries, preserves unrelated Python and matches a clean rebuild; repeated operation is idempotent. Current policy 5/schema 7 source/upgrade and installed public-fixture evidence pass. |
| REQ-QML-011-AC04 | `tests/test_qt_source_links_upgrade.py::test_req_qml011_ac04_removed_admission_removes_source_overlay`; `tests/test_qt_source_file_containment.py::test_req_qml011_ac04_unowned_file_sites_refresh_and_remove_stale_links`; `tests/test_qt_constructor_ownership.py::test_req_qml016_ac04_and_qml017_ac04_constructor_updates_remove_stale_sites_and_preserve_failures` | Actual cold/warm, manual update and watch, edit/removal, no-change repeat and unrelated facts. Supported constructor/member cases require full normalized parity; exact generic overload identity remains unproved and is not passed by native source-file comparison. |
| REQ-QML-012-AC02 | `tests/test_qt_source_links_upgrade.py::test_req_qml012_ac02_failed_source_links_upgrade_retains_products` (force off/on); constructor mutation/retention case above (manual/watch) | Real malformed-source rejection retains graph, manifest, analysis stamp and applicable root marker; corrected retry and repeat succeed. These cases supplement earlier actual cache/publication-failure regressions, rather than proving every persistence failure by one fixture. Source and current installed public-fixture retention pass. |
| REQ-QML-016-AC01/AC04 | `tests/test_qt_constructor_ownership.py::test_req_qml016_ac01_and_qml017_ac02_constructor_owns_emission_and_write_after_json_reload` (namespace/plain; directed/undirected); `tests/test_qt_constructor_ownership.py::test_req_qml016_ac04_constructor_conflicts_cannot_invent_a_canonical_owner`; constructor mutation/retention case above | Canonical constructor/source ownership through assembly, JSON reload, query and affected; no fabricated delivery call. Duplicate bodies, foreign namespaces and collapsed overloaded delegation retain unavailable native target proof. Inherited endpoint gap INC-QML-11 remains unverified. |
| REQ-QML-017-AC02/AC04 | The same exact constructor emission/write, conflict and mutation/retention tests | Literal accepted resource handles independently authorize QML access in a proven source callable; native class authority is not guessed from that access. Current reviewed source/wheel/public-fixture proof passes; unsupported dynamic handles/provider adoption remain separate gaps. |
| REQ-QML-019-AC02 | `tests/test_html_community_links.py::test_req_qml019_ac02_internal_only_group_has_source_edges_despite_zero_neighbors`; `tests/test_html_community_links.py::test_req_qml019_ac02_external_source_edges_are_distinct_from_neighbor_count`; `tests/test_html_community_links.py::test_req_qml019_ac02_isolated_source_member_does_not_claim_internal_connectivity`; `tests/test_html_community_links.py::test_req_qml019_ac02_source_edge_counts_keep_direction_parallel_edges_and_self_loops`; `tests/test_html_community_links.py::test_req_qml019_ac02_invalid_preaggregated_source_counts_remain_unavailable`; supplied-meta/small-view controls in that module | Eleven emitted-script/exporter cases pass. Counts use canonical graph edges, preserve source inputs and do not add fake plotted loops; unavailable counts, escaping and ordinary small-view Degree remain explicit. No new browser visual run is claimed. |

The source-site suite first failed seven cases before correction. The actual
facade source-file case then failed until the pipeline supplied explicit fresh
AST IDs; absent origin on borrowed nodes remains insufficient. The current
focused containment selection passes 63 cases in 9.56 seconds. Final six-module
source proof passes 90 cases in 14.70 seconds; final source-file/upgrade proof
passes 20 cases in 6.06 seconds. The final reviewed artifact broad suite passes
1044 cases with seven skips and one existing warning in 137.43 seconds. All 154
Python payloads match reviewed source, wheel and installation. The installed
public fixture rejects damaged source with force/partial options while preserving
four prior products, then repairs and repeats successfully. The HTML link
suite first failed six cases, then passes eleven; its related exporter/CLI
selection passes 172 cases. Commands and revision boundaries are in validation.

## Planned adoption criteria

Owner: Qt/QML integration maintainer. The three work packages are implemented;
their individual local source and installed acceptance is recorded below. This
heading retains its earlier external anchor. AC07 is a separate header discovery
contract; it does not borrow verification from the native syntax criterion.
The [INC-QML-08 plan](../docs/qt-qml/PLAN.md#inc-qml-08--installed-project-adoption-hardening)
records scope and exit checks. Original REQ-QML-001–017 hosted evidence applies to
its original bounded profile only. Every row here is locally verified for Windows
x64/Python 3.12; current hosted lanes remain unexecuted.

| Criterion | Evidence or exact remaining gap | Completion increment | Status |
| --- | --- | --- | --- |
| REQ-QML-018-AC01 | [Project/header adoption evidence](#project-and-header-adoption); [final combined installed profile](#final-adoption-delivery) | INC-QML-08a | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC02 | [Native syntax and cache upgrade evidence](../docs/qt-qml/VALIDATION.md#inc-qml-08a-native-source-compatibility); [reference-callable evidence](#declared-providers-and-reference-callables); final installed matrix below | INC-QML-08a/29 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC03 | [Declared provider and reference-callable evidence](#declared-providers-and-reference-callables); final installed matrix below | INC-QML-08b/29 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC04 | [Declared provider and reference-callable evidence](#declared-providers-and-reference-callables); logical direction and mechanism/callback integrity regressions; final installed matrix below | INC-QML-08b/30/36/37 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC05 | `tests/test_qt_combined_adoption.py::test_req_qml018_ac05_combined_configured_project_matches_cold_warm_and_updates`; four actual isolated installed CLI profiles and selected installed lifecycle suite; final matrix below | INC-QML-08c/32/38 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC06 | `tests/test_qt_combined_adoption_safety.py::test_req_qml018_ac06_combined_rejection_retains_cache_products_and_retries`; `tests/test_qt_combined_adoption_safety.py::test_req_qml018_ac06_combined_readonly_destination_preserves_then_retries`; direction/repeat/publication regressions mapped below; final installed matrix | INC-QML-08c/31–38 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |

## HTML community-view criteria

REQ-QML-019-AC01–AC03 retain local verification at the Python exporter/CLI and
emitted JavaScript boundaries. INC-QML-16 changes AC04 by removing Overview; its
current control acceptance is locally verified at emitted-script and reviewed
installed-artifact boundaries. Native browser/device behavior remains unverified.
Node harnesses execute production scripts with the external
vis network isolated; they prove dataset admission, controls and source payload,
not a new browser-engine or visual acceptance run. Installed-artifact identity and
executed commands are recorded in VALIDATION.md.

| Criterion | Exact production evidence | Increment | Status |
| --- | --- | --- | --- |
| REQ-QML-019-AC01 | `tests/test_html_community_recovery.py::test_req_qml019_ac01_large_export_recovers_complete_partition`; `tests/test_html_community_recovery.py::test_req_qml019_ac01_invalid_saved_membership_is_rebuilt_without_stale_names`; `tests/test_html_community_recovery.py::test_req_qml019_ac01_cli_exports_unclustered_saved_graph_without_sidecars`; `tests/test_html_community_recovery.py::test_req_qml019_ac01_explicit_graph_uses_adjacent_analysis_not_malformed_cwd_sidecar` | INC-QML-09 | Locally verified |
| REQ-QML-019-AC02 | `tests/test_html_community_recovery.py::test_req_qml019_ac02_existing_groups_get_missing_labels`; small/empty/authoritative group and name cases in the same module; `tests/test_qt_graph_html_payload.py::test_qml013_ac03_aggregated_html_explicitly_states_source_fact_omission`; existing escaping and written-node-info runtime regressions in `tests/test_export.py`; [current exact community-count assignments](#constructor-and-source-containment-corrections) | INC-QML-09; INC-QML-13 correction | Locally verified exporter/emitted-script counts and reviewed installed artifact; browser visual inspection is separate |
| REQ-QML-019-AC03 | `tests/test_html_community_recovery.py::test_req_qml019_ac03_invalid_computed_partition_preserves_output_and_recovers`; `tests/test_html_community_recovery.py::test_req_qml019_ac03_cli_unavailable_view_retains_prior_outputs_and_retries`; `tests/test_html_community_recovery.py::test_req_qml019_ac03_cli_failure_has_no_false_write_and_preserves_prior_html`; `tests/test_html_community_recovery.py::test_req_qml019_ac03_isolate_partition_over_hard_cap_is_not_published` | INC-QML-09 | Locally verified; actual atomic replacement failure injected at its OS boundary |
| REQ-QML-019-AC04 | `tests/test_html_initial_view.py::test_default_select_all_constructs_every_exported_node_and_edge_before_network`; `tests/test_html_initial_view.py::test_req_qml019_ac04_filters_all_none_preserve_endpoint_safe_source_data`; `tests/test_html_initial_view.py::test_req_qml019_ac04_search_restores_filtered_source_and_exact_metadata`; `tests/test_html_initial_view.py::test_small_grouped_and_ungrouped_views_default_to_select_all`; `tests/test_html_initial_view.py::test_req_qml019_ac04_partial_membership_cannot_mark_hidden_ungrouped_fact_selected` | INC-QML-09; INC-QML-16 removal | Locally verified current emitted-script controls and reviewed installed-artifact scripts. Native browser/device behavior unverified; earlier Overview results are revision-specific and superseded |

<a name="planned-project-membership-projection"></a>

## Project-membership projection

Owner: Qt project-metadata integration maintainer. INC-QML-14 owns all three
REQ-QML-020 criteria. Status: **Locally Verified for the bounded static public
profile**. The new production tests below have executed source, lifecycle,
consumer and reviewed installed-artifact evidence.
Current source/resource lookup, source-file containment and community edge counts
remain evidence for their existing boundary. Each independent membership site
must preserve declaration/target identity, direction, provenance and uncertainty
through the actual graph/consumer lifecycle. Qt policy 6/schema 7 at package
version 0.9.74 has source upgrade and reviewed installed public-fixture evidence.
Additional accepted-code-scope adoption checks pass; whole-root/provider/runtime
adoption gaps remain outside this closure.

| Criterion | Exact executed production evidence | Completion increment | Status |
| --- | --- | --- | --- |
| REQ-QML-020-AC01 | `tests/test_qt_project_membership.py::test_req_qml020_ac01_unused_component_has_persisted_build_and_resource_membership` (CMake/qmake; directed/undirected); `tests/test_qt_project_membership.py::test_req_qml020_ac01_metadata_spans_survive_bom_crlf_unicode_and_sanitation`; `tests/test_qt_project_membership.py::test_req_qml020_ac01_scoped_paths_repeated_declarations_and_query_keep_exact_identity`; `tests/test_qt_project_membership_updates.py::test_req_qml020_ac01_unused_packaged_component_survives_aggregate_export`. Targets uniquely accepted file/component endpoints, independent/repeated sites and same-name scoped files, `EXTRACTED` references, direction and original spans through facade/build/JSON reload/scoped query, unchanged loader/module lookup and actual aggregate-script membership counts. Source, consumer and final reviewed installed public-fixture evidence pass. | INC-QML-14 | Locally Verified (bounded static public profile) |
| REQ-QML-020-AC02 | `tests/test_qt_project_membership.py::test_req_qml020_ac02_source_projection_rejects_unproved_membership`; `tests/test_qt_project_membership.py::test_req_qml020_ac02_resources_reuse_existing_alias_guard_decisions`; `tests/test_qt_project_membership.py::test_req_qml020_ac02_corrupt_literal_transport_is_rejected`; `tests/test_qt_project_membership.py::test_req_qml020_ac02_location_prefix_cannot_authorize_another_source_span`; `tests/test_qt_project_membership.py::test_req_qml020_ac02_projection_reads_no_targets_and_executes_no_corpus`; `tests/test_qt_project_membership_updates.py::test_req_qml020_ac02_failed_metadata_join_preserves_products_and_recovers` (manual/force/watch); `tests/test_qt_project_membership_updates.py::test_req_qml020_ac02_join_exception_cannot_publish_partial_memberships`. Missing, duplicate, conditional, generated, wrong-role and out-of-root cases must have explicit status/reason and no target edge. The actual helper executes before injected failure; graph/manifest/analysis/root-marker bytes must remain unchanged. Projection guards target reads/discovery/process execution and preserves borrowed facts. All assigned source rejection/retention and final installed public-fixture checks pass. | INC-QML-14 | Locally Verified (bounded static public profile) |
| REQ-QML-020-AC03 | `tests/test_qt_project_membership.py::test_req_qml020_ac03_fresh_derived_sites_replace_borrowed_state_without_mutation`; `tests/test_qt_project_membership.py::test_req_qml020_ac03_typed_file_role_survives_punctuation_and_borrowed_publication`; `tests/test_qt_project_membership_updates.py::test_req_qml020_ac03_metadata_resource_and_source_updates_remove_stale_memberships` (manual/watch); `tests/test_qt_project_membership_updates.py::test_req_qml020_ac03_policy_upgrade_refreshes_unchanged_packaging` (extract/update); `tests/test_qt_project_membership_updates.py::test_req_qml020_ac03_membership_ids_are_independent_of_checkout_location`; `tests/test_qt_project_membership_updates.py::test_req_qml020_ac03_pipeline_publishes_replacement_without_borrowed_mutation`; malformed-resource recovery and aggregate-export tests above. Targets cold/warm/full/manual/watch parity, source edit/rename with metadata/alias updates, alias duplicates, target deletion, stale-edge removal, stable unrelated Python/relocated root identity, accepted typed-file identity through punctuation/publication, fresh-site replacement without borrowed mutation and policy-5 to policy-6 refresh without source/package changes. Complete source/lifecycle/consumer and reviewed installed public-fixture evidence pass for the bounded profile. | INC-QML-14 | Locally Verified (bounded static public profile) |

The first actual lifecycle selection failed all four cases in 3.76 seconds before
projection existed: the public fixture had no `membership_resolution` sites.
The failure record is baseline regression proof. Exact executed commands,
artifact identity and remaining broader limitations are in
[validation](../docs/qt-qml/VALIDATION.md#inc-qml-14-membership-projection).
The frozen source-projection module passes 26 cases in 1.90 seconds; its positive
facade cases fail twice with only projection disabled and actual parsing/indexes
retained. The reviewed-wheel checkpoint's combined selection passes 37 cases in
8.77 seconds. Two added directed graph variants then pass within a final
39-case focused selection in 9.50 seconds, with no production change. The
reviewed-wheel broad selection passes 1081 cases with seven documented skips and
one existing warning in 135.53 seconds. All 155 Python modules are byte-equal
between reviewed source, wheel and isolated installation. The installed public
CMake/qmake/qrc fixture has six resolved membership sites, accepted consumer/HTML
results, and actual force/partial failure retention followed by repair/repeat.
Browser visual, other-platform and executable Qt proof are not claimed. The
additional accepted-code-scope adoption refresh also passes. That INC-QML-14
checkpoint contained 81 criteria; the subsequent camera requirement adds three
without changing earlier criterion identities or revision evidence.

## Temporary middle-button camera and Overview removal

Owner: HTML viewer maintainer. INC-QML-16 owns REQ-QML-021-AC01–AC03 and the changed
REQ-QML-019-AC04, depending on the existing REQ-QML-019 community-view contract.
Status: **Locally verified at emitted-script and reviewed installed-artifact
boundaries; native browser/device and other-platform behavior unverified**.
The tests below execute the actual
emitted navigation script with a recording camera/network boundary; a stubbed
network does not establish a browser-engine, layout or native-device result.
The initial-view module separately retains checked startup, controls, dataset and
source metadata assertions while removing obsolete Overview expectations.

| Criterion | Exact production evidence and boundaries | Increment | Status |
| --- | --- | --- | --- |
| REQ-QML-021-AC01 | `tests/test_html_middle_pan.py::test_req_qml021_ac01_middle_drag_translates_both_axes_at_current_zoom` (24 horizontal/vertical/diagonal, four-scale, source/aggregate variants); incremental client delta divided by current zoom, preserved scale, no animation, and suppressed native middle autoscroll | INC-QML-16 | Locally verified emitted-script and reviewed installed-artifact boundary; native browser/device and other platforms unverified |
| REQ-QML-021-AC02 | `tests/test_html_middle_pan.py::test_req_qml021_ac02_release_cancel_blur_and_lost_buttons_end_drag`; `tests/test_html_middle_pan.py::test_req_qml021_ac02_capture_failure_has_window_fallback_and_no_lingering_drag`; `tests/test_html_middle_pan.py::test_req_qml021_ac02_invalid_camera_or_input_aborts_without_jump`; `tests/test_html_middle_pan.py::test_req_qml021_ac02_invalid_press_cannot_capture_or_resume_after_repair`; `tests/test_html_middle_pan.py::test_req_qml021_ac02_unrelated_pointer_and_nonmiddle_release_preserve_owned_drag`. Matching release/cancel, lost button/capture, blur/pagehide, outside movement/capture fallback, invalid finite/scale/derived-position and cursor restoration controls prove termination and no later jump | INC-QML-16 | Locally verified emitted-script and reviewed installed-artifact boundary; native browser/device and other platforms unverified |
| REQ-QML-021-AC03 | `tests/test_html_middle_pan.py::test_req_qml021_ac03_other_inputs_and_source_datasets_remain_unchanged`; `tests/test_html_middle_pan.py::test_req_qml021_ac03_filters_and_search_work_after_middle_drag`; left/right/touch/wheel coexistence and actual startup/filter/all/none/search/inspector controls preserve graph/payload/dataset metadata, node positions, physics and temporary camera-only state | INC-QML-16 | Locally verified emitted-script and reviewed installed-artifact boundary; native browser/device and other platforms unverified |

The focused command executes both current modules:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_html_middle_pan.py tests/test_html_initial_view.py --tb=short -rs
```

Result: **60 passed**, 6.57 seconds, with no skips, after restoring retained Qt
projection, metadata/span/attribute and endpoint-safe source-edge assertions.
The earlier 60-pass/6.71-second checkpoint precedes that assertion review; the
44-pass/4.99-second checkpoint precedes independent horizontal/vertical/diagonal expansion.
An earlier missing-hook selection has 28 failed cases; the integration owner's validation record owns its
exact command/revision. Earlier exporter/CLI/membership-consumer regression proof
passes 219 cases in 54.20 seconds before the sixteen additional geometry cases.
The final exporter/CLI/membership/inspector selection passes 231 cases in 53.15
seconds, without failures or skips.
Wheel-artifact/Qt HTML consumers pass seven cases in 4.60 seconds, and the legacy
export module passes 67 cases in 2.95 seconds. These recorded script/artifact
boundaries do not close native browser/device behavior. The final 231-case
selection and seven additional consumer/wheel cases cover 238 distinct cases.
Five touched owners pass Ruff; the four navigation/source/test owners pass
explicit-runtime Pyright with zero errors/warnings. Including the legacy
`tests/test_export.py` owner reports one unchanged `reportOptionalOperand` error
at line 1008, reproduced against the prior revision with the same explicit
include/exclude configuration. The narrow listener-registration adjustment does
not alter that optional-return expression, inspector assertions or type checks.

The reviewed production tree is `a991dd9fb2d638cf15fbb2c76499ed1f6ebd51ea`; wheel
SHA256 is `11e370a19d328a01b4e9e30726731c815b4ef58399833ff3d0a7c644f71e98f0`.
All 156 Python payloads match reviewed source, wheel and isolated installation.
The installed viewer artifact retains canonical/RAW data, checked startup and
source inspectors; actual emitted-script camera moves and release/blur/retry
cleanup pass. No private input identifiers, paths or source are retained here.
Helper/HTML/initial-view/middle-pan measurements are 116/789/245/223 physical lines;
the updated inspector harness remains within its documented 1377-line exception.
Qt policy 6 and AST schema 7 are unchanged; this is viewer input, with no source
execution, new SDK, persistence operation or graph diagnostic. Earlier Overview
and camera selection evidence is historical. A changed requirement is verified
only after its own applicable controls and failure/cleanup cases pass; broader
adoption, inherited endpoint and constructor-overload gaps remain independent.

## Follow-up audit scope corrections

Inspected production revision: `95adbdc165f44a96bf275a7870bb1da4d82a5bea`.
Public static fixtures; Python 3.12.14, tree-sitter 0.25.2 and language-pack 0.11.0;
Windows. No Qt SDK or corpus execution. The probes are explicit opt-in diagnostic
tests and retain correct failing assertions. Their default-discovery exclusion is
temporary audit ownership, not regression completion. The correction owner must
promote them into normal collection and reverify all affected criteria.

| Acceptance | Exact probe or system assignment | Outcome / correction owner |
| --- | --- | --- |
| REQ-QML-017-AC02/AC04 | `tests/audit/probe_qt_qml_object_boundaries.py::test_cpp_reflective_child_property_does_not_inherit_qml_lexical_root` (read/write/invoke variants) | Three persisted-edge rejections fail; INC-QML-17 reverse-access resolver owner |
| REQ-QML-017-AC02/AC04 | `tests/audit/probe_qt_qml_object_boundaries.py::test_cpp_findchild_does_not_search_sibling_outside_receiver_subtree`; `tests/audit/probe_qt_qml_object_boundaries.py::test_cpp_findchild_direct_search_cannot_select_grandchild` | Both persisted-edge rejections fail; INC-QML-17 |
| REQ-QML-017-AC03/AC04 | `tests/audit/probe_qt_qml_object_boundaries.py::test_disjoint_engine_scopes_cannot_supply_context_provider` | Provider edge reaches another engine; rejection fails; INC-QML-18 context integration owner |
| REQ-QML-017-AC02/AC03 | `tests/audit/probe_qt_qml_object_boundaries.py::test_public_receiver_and_engine_positive_controls` | Own-object/root/engine controls pass; they do not validate failing scopes |
| REQ-QML-018-AC03 | `tests/audit/probe_qt_qml_object_boundaries.py::test_pending_typed_factory_provider_remains_unresolved` | Historical baseline exclusion only at 95adbdc; superseded by ordinary positive typed-provider regressions in INC-QML-08b. This opt-in probe is not current acceptance |
| REQ-QML-016-AC02/AC03/AC04 | `tests/audit/probe_qt_native_type_shadowing.py::test_req_qml016_connect_alias_cannot_select_unrelated_global_signal` (using/typedef); `tests/audit/probe_qt_native_type_shadowing.py::test_req_qml016_block_alias_does_not_change_before_and_after_native_scope` | Three wrong persisted-endpoint cases fail; INC-QML-19 native type/endpoint owners |
| REQ-QML-016-AC01/AC03/AC04 | `tests/audit/probe_qt_native_type_shadowing.py::test_req_qml016_emission_alias_cannot_select_unrelated_global_signal` (using/typedef) | Two wrong emission endpoints fail; INC-QML-19 |
| REQ-QML-008-AC01/AC03 | `tests/audit/probe_qt_native_type_shadowing.py::test_req_qml008_alias_registration_cannot_export_global_class_to_qml` (using/typedef) | Two wrong native-to-QML registration/handler cases fail; INC-QML-19 |
| REQ-QML-008-AC01 and REQ-QML-016-AC01/AC02/AC04 | `tests/audit/probe_qt_native_type_shadowing.py::test_direct_native_type_control_preserves_roles_and_direction`; `tests/audit/probe_qt_native_type_shadowing.py::test_direct_registration_control_preserves_native_qml_endpoint` (Sender/Other variants) | Four direct native/QML controls pass through actual publication and directed reload |
| REQ-QML-021-AC01–AC03 and REQ-QML-019-AC04 | [Native navigation review procedure](../docs/qt-qml/VIEWER_SYSTEM_REVIEW.md) | Exact fixture/actions/evidence/failure/cleanup/owner defined; physical browser/device/platform execution remains unverified |
| REQ-QML-017-AC01/AC04 | `tests/audit/probe_qt_loader_forms.py::test_req_qml017_ac01_literal_loader_keeps_component_and_property_provenance` (engine URL constructor/component loadUrl/engine.load variants) | Two loader-admission assertions fail; engine.load control passes; INC-QML-20 collector/integration owner |

Executed command:

```text
.venv/Scripts/python.exe -X utf8 -m pytest tests/audit/probe_qt_qml_object_boundaries.py tests/audit/probe_qt_native_type_shadowing.py tests/audit/probe_qt_loader_forms.py -q --tb=short
```

Final combined result: **15 failed, 7 passed in 3.38 seconds**, one existing Hypothesis collection
warning. Thirteen failing variants expose four wrong-target root causes; two more expose loader omissions.
The independent existing lifecycle selection passed **67 tests in 21.43 seconds**;
the final native/QML compatibility selection passed **60 tests in 4.85 seconds**.
Neither establishes cold/warm/manual/watch parity for a correction not implemented.
At that baseline audit, reviewed installed-wheel, complete repository suite and
new hosted proof were unexecuted for the corrections. Current per-increment
package proof and repository gate failures are recorded in validation; new hosted
proof remains unexecuted. See [audit](../docs/qt-qml/FOLLOWUP_AUDIT.md)
and [plan](../docs/qt-qml/PLAN.md) for scope, dependencies and delivery gates.

## Receiver correction evidence (INC-QML-17)

These current mappings supplement the historical audit/profile rows above.
The reviewed installed artifact passes 98 selected cases with no skips/failures;
exact wheel identity and dependency limits are in
[validation](../docs/qt-qml/VALIDATION.md#inc-qml-17-receiver-ownership-and-construction-trees).
Full contribution gates ran at INC-QML-20; documented baseline failures remain.

| Acceptance | Automatically collected production evidence | Current boundary |
| --- | --- | --- |
| REQ-QML-017-AC02 | `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_child_reflection_cannot_use_lexical_root`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_findchild_rejects_siblings_depth_and_receiver`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_property_held_qobject_has_construction_owner`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac04_native_base_members_and_property_child_keep_source_proof`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_inherited_member_is_receiver_owned_and_readonly_write_rejected` | Partial; receiver correction passes; static reflection correction has separate INC-QML-22 evidence below |
| REQ-QML-017-AC02/AC04 | `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_duplicate_names_are_ambiguous_only_inside_receiver`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_parent_bindings_and_js_writes_do_not_authorize_construction_tree`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_unknown_types_and_component_templates_remain_unavailable`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_construction_lookup_requires_accepted_declaration_proof`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_proved_cpp_parent_mutation_keeps_source_but_no_target`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_unsupported_findchild_options_cannot_choose_target`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_unproved_findchild_type_filter_cannot_choose_object`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_noncreatable_singleton_and_gadget_cannot_prove_qobject_creation` | Rejection/ambiguity and accepted source-construction proof pass without guessed targets |
| REQ-QML-017-AC04 | `tests/test_qt_semantic_correction_updates.py::test_req_qml017_ac04_receiver_tree_and_member_updates_remove_stale_edges`; `tests/test_qt_semantic_correction_updates.py::test_req_qml017_ac04_policy_refresh_failure_retains_products_and_retry`; `tests/test_qt_semantic_correction_updates.py::test_req_qml017_ac04_failed_completion_keeps_prior_graph_and_retries` | Partial; bounded receiver/provider/loader lifecycle passes; INC-QML-21/22 have separate evidence below; wider system gaps remain |

Existing QML scope/declaration/identity, loader, provider and reverse-update tests
also pass against that reviewed wheel. Factory providers, inherited native signal
ancestors and generic overload identity retain their separately recorded gaps.

## Declaration identity correction evidence (INC-QML-18)

These ordinary collected regressions replace A12's opt-in reproduction as current
acceptance evidence. Native/system lifetime and broader provider adoption remain
explicit gaps; the source profile does not execute a Qt engine.

| Acceptance | Exact production-boundary test | Observable evidence |
| --- | --- | --- |
| REQ-QML-017-AC03; REQ-QML-008-AC01 | `tests/test_qt_engine_identity.py::test_req_qml017_ac03_disjoint_same_named_engines_cannot_share_provider`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_same_engine_positive_retains_persisted_provider`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_nested_engine_shadow_does_not_receive_outer_provider`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_local_provider_lifetime_cannot_supply_later_load`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_engine_and_provider_parameters_have_exact_identity` | Disjoint/nested engines and expired providers have no persisted binding; exact local/parameter positive controls retain component and native property endpoints |
| REQ-QML-017-AC03/AC04 | `tests/test_qt_engine_identity.py::test_req_qml017_ac03_rejected_identity_preserves_precise_source_diagnostic`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_initial_properties_report_only_shared_identity_failure`; `tests/test_qt_engine_identity.py::test_req_qml017_ac04_writes_and_duplicate_declarations_fail_closed`; `tests/test_qt_engine_identity.py::test_req_qml017_ac04_conditional_and_deferred_lifetimes_have_no_identity`; `tests/test_qt_engine_identity.py::test_req_qml017_ac04_missing_or_corrupted_transport_cannot_fall_back_to_name` | Source-owned rejection reasons, mixed initial properties and corrupted transport never authorize a name-based fallback |
| REQ-QML-017-AC04 | `tests/test_qt_engine_identity.py::test_req_qml017_ac04_auto_and_explicit_handles_keep_declaration_identity`; `tests/test_qt_engine_identity.py::test_req_qml017_ac04_ids_are_portable_with_original_unicode_bom_crlf_spans`; `tests/test_qt_engine_identity_updates.py::test_req_qml017_ac04_engine_scope_changes_remove_stale_provider_links`; `tests/test_qt_engine_identity_updates.py::test_req_qml017_ac04_malformed_identity_source_retains_products_and_retries`; `tests/test_qt_engine_identity_updates.py::test_req_qml017_ac04_directed_query_affected_and_reload_keep_scoped_provider` | Partial; bounded receiver/provider/loader lifecycle passes; INC-QML-21/22 have separate evidence below; wider system gaps remain |

Exact source/artifact commands and outcomes belong to the corresponding validation
section. Full contribution gates run at the INC-QML-20 integration boundary.

## Native alias and ancestry correction evidence (INC-QML-19)

Ordinary collected cases supersede A13's opt-in probe as current bounded source
evidence. Imported-header targets, inherited event endpoints and generic overload
identity remain explicitly excluded or assigned to INC-QML-11/15.

| Acceptance | Exact test | Evidence |
| --- | --- | --- |
| REQ-QML-016-AC01/AC02/AC03/AC04 | `tests/test_qt_native_alias_scope.py::test_req_qml016_connect_alias_cannot_select_unrelated_global_signal`; `tests/test_qt_native_alias_scope.py::test_req_qml016_emission_alias_cannot_select_unrelated_global_signal`; `tests/test_qt_native_alias_scope.py::test_req_qml016_block_alias_does_not_change_before_and_after_native_scope`; `tests/test_qt_native_alias_scope.py::test_direct_native_type_control_preserves_roles_and_direction`; `tests/test_qt_native_alias_scope.py::test_namespace_lookup_and_namespace_alias_keep_original_byte_spans` | Source-local alias rejection/positive controls preserve canonical roles, relation distinctions and original spans |
| REQ-QML-008-AC01/AC03 | `tests/test_qt_native_alias_scope.py::test_req_qml008_alias_registration_cannot_export_global_class_to_qml`; `tests/test_qt_native_alias_scope.py::test_direct_registration_control_preserves_native_qml_endpoint`; `tests/test_qt_native_alias_scope.py::test_proven_alias_registration_exports_the_actual_class_and_qml_signal`; `tests/test_qt_native_alias_scope.py::test_local_alias_positive_and_rejection_profile` | Registration/QML projections select accepted aliases or retain no guessed provider |
| REQ-QML-016-AC01–AC04; REQ-QML-008-AC01/AC03 | `tests/test_qt_native_alias_updates.py::test_alias_type_edit_and_removal_refreshes_native_qml_cold_warm_consumers`; `tests/test_qt_native_alias_updates.py::test_unprovable_alias_replaces_old_edges_without_global_name_fallback`; `tests/test_qt_native_alias_updates.py::test_bad_native_alias_input_retains_outputs_then_recovers_and_repeats`; `tests/test_qt_native_alias_updates.py::test_accepted_header_alias_cannot_resolve_outer_global_native_or_qml_endpoint`; `tests/test_qt_native_alias_updates.py::test_transitive_header_alias_owns_shadow_but_not_prior_source_use`; `tests/test_qt_native_alias_updates.py::test_included_alias_fact_corruption_rejects_provenance_instead_of_resolving_outer_type`; `tests/test_qt_native_alias_updates.py::test_fresh_alias_header_uses_borrowed_qt_context_without_mutating_it` | Real manual/watch full/cold/warm, stale-edge removal, persisted/query/affected, parse/write failure retention and retry; included alias provenance rejection and borrowed-context isolation |
| REQ-QML-017-AC02/AC04 | `tests/test_qt_construction_authority.py::test_req_qml017_ac02_widget_and_unknown_ancestry_cannot_authorize_child_tree`; `tests/test_qt_construction_authority.py::test_req_qml017_ac04_direct_and_source_defined_qobject_chain_survives_publication`; `tests/test_qt_construction_authority.py::test_req_qml017_ac02_native_ancestry_reads_only_accepted_complete_source_facts`; `tests/test_qt_construction_authority.py::test_req_qml017_ac04_parent_mutation_spans_are_bounded_original_bytes`; `tests/test_qt_reflection_type_aliases.py::test_req_qml017_ac02_findchild_filter_rejects_shadowed_sdk_type` | Widget/unknown/corrupt/native shadow rejection; direct/derived non-widget controls, original 50/51 mutation-span boundary and unshadowed QObject filter |

Exact executed source/artifact evidence is retained in validation; whole-requirement
verification remains bounded by recorded adoption/inheritance/overload/system gaps.

At the INC-QML-19 checkpoint same-file qualified canonical classes remained an
implementation gap under REQ-QML-008-AC02, REQ-QML-016-AC01/AC04 and
REQ-QML-017-AC02/AC04. The original negative control proved safe rejection.
INC-QML-21 adds independent producer identities and collected proof/update cases
below; the genuine same-file native-versus-widget assertion now proves exact
ownership without weakening the unrelated rejection controls.

## Literal loader correction evidence (INC-QML-20)

| Acceptance | Exact ordinary test | Evidence |
| --- | --- | --- |
| REQ-QML-017-AC01/AC04 | `tests/test_qt_loader_provenance.py::test_req_qml017_ac01_literal_loader_keeps_component_and_property_provenance` | Existing engine.load control, URL engine constructor and component loadUrl/create retain original source spans, component/property targets and persisted direction |
| REQ-QML-017-AC01/AC04 | `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_supported_loader_overloads_have_one_source`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_local_file_wrapper_cannot_become_resource_url`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_absolute_fromlocalfile_retains_file_component`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_url_wrapper_shadow_cannot_lend_literal_argument`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_custom_component_engine_cannot_authorize_constructor`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_global_sdk_constructor_bypasses_namespace_shadow`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_sdk_name_shadow_cannot_authorize_loader`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac04_unknown_overload_or_creation_cannot_prove_root`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_constructor_mode_needs_sdk_type_authority`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_string_wrapper_requires_source_authority` | Literal controls, parent/mode/context boundaries, absolute file vs resource/relative/computed URLs and source-defined class/alias/callable rejection |
| REQ-QML-017-AC03/AC04 | `tests/test_qt_loader_providers.py::test_req_qml017_ac03_component_load_url_uses_its_exact_engine_provider`; `tests/test_qt_loader_providers.py::test_req_qml017_ac03_component_engine_shadow_cannot_borrow_another_provider`; `tests/test_qt_loader_providers.py::test_req_qml017_ac03_component_engine_assignment_condition_and_factory_reject` | Named/context-object provider joins use exact component-owned engine identity; shadows/reassignment/conditional/factory results cannot lend provider authority |
| REQ-QML-017-AC04 | `tests/test_qt_loader_updates.py::test_req_qml017_ac04_loader_edits_match_cold_warm_manual_and_watch`; `tests/test_qt_loader_updates.py::test_req_qml017_ac04_loader_parse_failure_preserves_products_and_recovers`; `tests/test_qt_loader_updates.py::test_req_qml017_ac04_loader_write_failure_preserves_products_and_retries`; `tests/test_qt_loader_updates.py::test_req_qml017_ac04_loader_directed_reload_query_and_affected_keep_endpoints` | Real source/resource/member edits and removal, cold/warm/manual/watch parity, stale-edge removal, four-product parse/replace failure retention, repaired retry/idempotency and actual persisted query/affected endpoints |
| REQ-QML-001-AC01/AC02; REQ-QML-003-AC01 | `tests/test_languages.py::test_qml_language_facade_preserves_source_declarations_and_spans` | CONTRIBUTING language convention, production facade and hand-checked declaration/original-byte spans; optional-parser absence is explicit skip, not acceptance |

The INC-QML-20 checkpoint retained failing opt-in INC-QML-22 cases under REQ-QML-017-AC02/AC04:
`tests/audit/probe_qt_reflection_type_shadowing.py::test_req_qml017_ac02_shadowed_reflection_type_cannot_create_qml_target`
and its positive control
`tests/audit/probe_qt_reflection_type_shadowing.py::test_req_qml017_ac04_unshadowed_sdk_reflection_preserves_targets_and_provenance`.
At the audited baseline twelve failures and two passes established the gap.
The opt-in probe remains excluded historical evidence; the ordinary INC-QML-22
regressions below now exercise the corrected rejection and positive controls.

The INC-QML-20 checkpoint retained the actual Windows failure assigned to INC-QML-23:
`tests/test_atomic_writes.py::test_write_text_atomic_refuses_a_readonly_destination_without_leaking_a_temp`
under REQ-QML-018-AC06. It failed on the original baseline and INC-QML-20
checkpoint. INC-QML-23/25 ordinary tests below cover the corrected actual OS
retention and caller completion boundary; wider adoption remains unverified.

## Follow-up correction evidence (INC-QML-21–27)

These cases extend the bounded profile; they do not close all wider adoption,
inherited-endpoint or overload criteria. Exact final commands, installed artifact
identity and contribution gate limitations are recorded in validation.

| Acceptance IDs | Ordinary production-boundary tests | Evidence scope |
| --- | --- | --- |
| REQ-QML-008-AC02; REQ-QML-016-AC01/AC04; REQ-QML-017-AC02/AC04 | `tests/test_cpp_qualified_identity.py::test_req_qml008_ac02_qualified_class_bodies_keep_distinct_portable_identities`; `tests/test_cpp_qualified_proof.py::test_req_qml008_ac02_using_namespace_bound_cannot_discard_competing_owner`; `tests/test_cpp_qualified_updates.py::test_req_qml017_ac04_qualified_owner_edits_match_cold_warm_updates_and_consumers` | Qualified IDs/body proof, signature/cap rejection, original bytes, canonical calls/emissions, full/manual/watch and affected preservation |
| REQ-QML-017-AC02/AC04 | `tests/test_qt_reflection_type_identity.py::test_req_qml017_ac02_shadowed_reflection_type_cannot_create_qml_target`; `tests/test_qt_reflection_type_identity.py::test_req_qml017_ac04_sdk_reflection_query_and_affected_use_exact_persisted_site`; `tests/test_qt_reflection_updates.py::test_req_qml017_ac04_reflection_source_qml_metadata_edits_remove_stale_targets`; `tests/test_qt_reflection_updates.py::test_req_qml017_ac04_reflection_parse_failure_retains_four_products_and_recovers`; `tests/test_qt_reflection_updates.py::test_req_qml017_ac04_reflection_write_failure_retains_four_products_and_retries` | Collected replacement for excluded reflection probe; strict whole-graph lifecycle and real failure/retry |
| REQ-QML-017-AC01/AC04 | `tests/test_qt_loader_sdk_declarations.py::test_req_qml017_ac01_incomplete_sdk_declaration_cannot_authorize_loader`; `tests/test_qt_loader_sdk_declarations.py::test_req_qml017_ac04_uncertain_sdk_use_retains_observed_loader`; `tests/test_qt_loader_sdk_declarations.py::test_req_qml017_ac04_loader_forward_edits_retire_and_restore_targets`; `tests/test_qt_loader_sdk_declarations.py::test_req_qml017_ac04_loader_forward_failure_retains_products_and_recovers` | SDK/source controls through JSON reload, full/manual/watch edits, uncertain facts, stale-edge removal and durable parse/publication recovery |
| REQ-QML-018-AC06; REQ-QML-011-AC04; REQ-QML-013-AC03 | `tests/test_atomic_replace_retention.py::test_req_qml018_ac06_readonly_rejects_without_displacing_destination`; `tests/test_atomic_replace_retention.py::test_req_qml018_ac06_fallback_failure_restores_prior_state`; `tests/test_atomic_replace_retention.py::test_req_qml018_ac06_restore_failure_keeps_recovery_backup`; `tests/test_qt_readonly_publication.py::test_req_qml018_ac06_readonly_graph_preserves_products_then_retries` | Actual Windows OS read-only failure, fallback ordering, retention and guarded caller retry; system/platform gaps remain separate |
| REQ-QML-012-AC02; REQ-QML-018-AC06; REQ-QML-011-AC04 | `tests/test_qt_product_publication.py::test_inc25_readonly_each_product_preserves_cohort_and_retries`; `tests/test_qt_product_publication.py::test_inc25_preparation_and_late_replace_faults_preserve_then_retry`; `tests/test_qt_product_publication.py::test_inc25_first_build_failure_publishes_no_acceptance_products`; `tests/test_publication.py::test_inc25_actual_rollback_fault_retains_recovery_copies`; `tests/test_publication.py::test_inc25_cleanup_failure_does_not_misreport_cohort_authority` | Actual durable acceptance cohort, first-build and later-stage failures, rollback integrity/cleanup and independent valid AST cache boundary |
| REQ-QML-011-AC02/AC04; REQ-QML-017-AC04 | `tests/test_qt_orphan_cleanup.py::test_req_qml017_ac04_watch_restored_sdk_source_has_no_stale_generic_placeholder`; `tests/test_qt_orphan_cleanup.py::test_req_qml011_ac04_complete_refresh_keeps_semantic_connected_and_hyperedge_stub_context`; `tests/test_qt_orphan_cleanup.py::test_req_qml011_ac04_partial_refresh_is_not_authority_to_remove_placeholder` | Strict full graph parity, immutable borrowed state and preserved live/semantic/hyperedge/source ownership |
| REQ-QML-007-AC01/AC03; REQ-QML-008-AC02/AC03; REQ-QML-017-AC03/AC04 | `tests/test_qt_native_property_notify.py::test_req_qml007_ac03_native_property_handler_maps_custom_and_conventional_notify`; `tests/test_qt_native_property_notify.py::test_req_qml008_ac02_shared_notify_preserves_two_independent_handler_sites`; `tests/test_qt_native_property_notify.py::test_req_qml007_ac03_notify_binds_only_block_injection_or_explicit_formals`; `tests/test_qt_native_property_notify.py::test_req_qml017_ac04_native_notify_query_and_affected_use_canonical_signal` | Real canonical signal/provider subscriptions, invalid notify rejection, explicit/legacy binding, reload/query/affected; wider native inheritance remains unverified |

The [exposure chapter review](../docs/qt-qml/EXPOSURE_CHAPTER_REVIEW.md) names the
official mechanism checklist. Macro accountability is separately recorded in the
API inventory. Excluded audit probes remain historical evidence and cannot by
themselves verify release acceptance. Corrected scenarios use ordinary discovery.

Native parameter/lifecycle mappings additionally cover:

| Acceptance IDs | Exact collected test | Scope |
| --- | --- | --- |
| REQ-QML-007-AC01/AC03 | `tests/test_qml_handler_formals.py::test_req_qml007_ac03_source_handler_formals_preserve_property_dependency`; `tests/test_qml_handler_formals.py::test_req_qml007_ac03_handler_authority_survives_parameter_display_limit`; `tests/test_qml_handler_formals.py::test_req_qml007_ac03_signal_parameter_overflow_rejects_without_truncation`; `tests/test_qml_handler_formals.py::test_req_qml007_ac03_handler_change_does_not_reclassify_unrelated_javascript` | Pure-QML/native explicit binding, display bounds and unchanged ordinary JS classification |
| REQ-QML-007-AC03; REQ-QML-008-AC02/AC03; REQ-QML-017-AC03/AC04 | `tests/test_qt_native_notify_updates.py::test_req_qml017_ac04_notify_edits_remove_stale_edges_with_full_parity`; `tests/test_qt_native_notify_updates.py::test_req_qml017_ac04_notify_parse_failure_retains_products_and_recovers`; `tests/test_qt_native_notify_updates.py::test_req_qml017_ac04_notify_manifest_failure_rolls_back_and_retries` | Cold/warm, directed/default, source/QML/qmake edits, manual/force/watch rejection and post-graph sidecar rollback/recovery |

| Acceptance IDs | Exact collected included-header/setup test | Scope |
| --- | --- | --- |
| REQ-QML-017-AC01/AC04 | `tests/test_qt_loader_header_shadows.py::test_req_qml017_ac01_included_forward_class_blocks_sdk_loader_and_wrapper_authority`; `tests/test_qt_loader_header_shadows.py::test_req_qml017_ac04_header_only_forward_edits_match_cold_warm_and_restore`; `tests/test_qt_loader_header_shadows.py::test_req_qml017_ac04_header_shadow_failure_preserves_products_and_retries`; `tests/test_qt_loader_header_shadows.py::test_req_qml017_ac04_class_shadow_walk_overflow_rejects_instead_of_discarding_header` | Accepted literal include/provenance shadows, independent native target roles, header-only lifecycle, failure/retry and 129-header rejection |
| REQ-QML-012-AC02; REQ-QML-018-AC06 | `tests/test_publication.py::test_inc25_setup_fault_has_safe_code_and_preserves_retry`; `tests/test_publication.py::test_inc25_partial_setup_cleanup_fault_retains_safe_recovery_evidence`; `tests/test_qt_product_publication.py::test_inc25_successful_ast_cache_does_not_authorize_failed_products` | Safe destination/setup diagnostics, owned partial setup cleanup and unchanged original successful cache-entry bytes with valid new entries |

Final source and installed acceptance for INC-QML-21–27 is recorded in
[validation](../docs/qt-qml/VALIDATION.md#final-local-follow-up-integration-evidence).
All executed correction cases pass. The installed publication symlink case,
existing atomic symlink/mode and external-symlink admission cases remain explicit
host gaps; optional language skips do not establish acceptance. Full repository
pytest and typing retain the separately recorded baseline failures. Broader
adoption/inherited native endpoint/overload criteria remain Partially verified.


## Inherited endpoints and pending adoption integration

| Acceptance ID | Exact production-boundary evidence | State |
| --- | --- | --- |
| REQ-QML-016-AC01 | `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac01_grandparent_endpoints_use_declaring_members`; `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac01_diamond_deduplicates_declarations_and_rejects_conflicts`; `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac01_shadowing_precedes_role_signature_and_visibility`; `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac01_ancestor_traversal_has_a_fail_closed_32_class_budget`; `tests/test_qt_inherited_access.py::test_req_qml016_ac01_external_member_pointer_cannot_cross_nonpublic_base`; missing/corrupt access and lexical namespace controls in those modules | Locally verified inherited declaration/access profile; explicit missing-declaration emissions remain INC-QML-28 |
| REQ-QML-016-AC04 | `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac04_ancestor_edges_reach_reload_query_and_affected`; `tests/test_qt_inherited_updates.py::test_req_qml016_ac04_header_signal_base_and_site_edits_match_full_cold_warm`; `tests/test_qt_inherited_updates.py::test_req_qml016_ac04_malformed_ancestor_preserves_products_then_retries`; `tests/test_qt_inherited_updates.py::test_req_qml016_ac04_readonly_ancestor_refresh_preserves_cohort_and_retry` | Local manual/watch, reload/query/affected and real failure/retry pass; reviewed installed suite passes; wider hosted matrix unverified |
| REQ-QML-018-AC07 | [Project/header adoption evidence](#project-and-header-adoption) | Local source/update pass; reviewed installed suite passes; wider hosted matrix unverified |

Current adoption criterion count is seven, bringing the catalog to 85 acceptance
criteria across 21 requirements. Earlier six-criterion counts describe the earlier
profile. No criterion is renumbered. Runtime execution, arbitrary include search,
Qt SDK equivalence and other platforms remain outside this bounded static proof.

## Exact constructor overloads

| Acceptance IDs | Exact ordinary production tests | State and boundary |
| --- | --- | --- |
| REQ-QML-008-AC02 | `tests/test_cpp_overload_identity.py::test_req_qml008_ac02_overload_producer_ids_spans_and_exact_declaration_merge`; `tests/test_cpp_overload_identity.py::test_req_qml008_ac02_constructor_ids_survive_overload_addition_removal_and_parameter_rename`; `tests/test_cpp_overload_identity.py::test_req_qml008_ac02_distinct_pointer_reference_and_builtin_types_never_collapse`; `tests/test_cpp_overload_type_authority.py::test_req_qml008_ac02_shadow_transport_spans_address_original_bom_crlf_unicode_bytes`; `tests/test_qt_overload_consumers.py::test_req_qml008_ac02_and_qml011_ac01_exact_overload_native_consumers` | Local producer/facade/source/export/query/affected pass; exact accepted signature and original-span profile. Reviewed installed suite passes; wider hosted matrix unverified. |
| REQ-QML-008-AC03 | `tests/test_cpp_overload_identity.py::test_req_qml008_ac03_unsupported_signatures_keep_visible_distinct_occurrences_without_owner`; `tests/test_cpp_overload_identity.py::test_req_qml008_ac03_qualified_void_cannot_authorize_zero_argument_constructor`; `tests/test_cpp_overload_type_authority.py::test_req_qml008_ac03_angle_local_shadow_cannot_grant_sdk_constructor_identity`; `tests/test_cpp_overload_type_authority.py::test_req_qml008_ac03_include_walk_overflow_cannot_hide_sdk_shadow`; `tests/test_qt_overload_consumers.py::test_req_qml008_ac03_unknown_overload_signature_cannot_borrow_known_native_class` | Local uncertainty, duplicate/type/include/transport rejection pass. Aliases, templates, dependent/function-pointer/array/variadic signatures remain unsupported. |
| REQ-QML-011-AC01 | `tests/test_cpp_overload_updates.py::test_req_qml011_ac01_ac04_overload_signature_edit_removal_and_repeat_parity`; `tests/test_qt_overload_consumers.py::test_req_qml008_ac02_and_qml011_ac01_exact_overload_native_consumers` | Local cold/warm/full/manual/watch, exact native ownership and canonical consumer parity pass. |
| REQ-QML-011-AC04 | `tests/test_cpp_overload_updates.py::test_req_qml011_ac04_overload_publication_failure_retains_cohort_and_retries`; `tests/test_cpp_overload_updates.py::test_req_qml011_ac04_partial_constructor_parse_retains_accepted_identity_and_recovery`; `tests/test_cpp_overload_updates.py::test_req_qml011_ac04_schema9_name_id_fixture_migrates_unchanged_sources_to_exact_signatures` | Real OS and injected late publication failure, nonempty real cache retention, repair/repeat and modeled schema-9 name-ID fixture migration pass. This fixture models the old identity seam; it is not a replay of every old release semantic. |

Former blanket overloaded-constructor rejection is superseded by this accepted
signature profile. Existing ownership rejection tests now use duplicate equivalent
signatures; they retain their exact-owner and corruption assertions. Delegation
keeps the actual body owner without inventing a direct delegation call. The
reference-return callable omission remains a separate INC-QML-29 gap under
REQ-QML-018-AC02/AC03 until its ordinary producer regression passes.

Source integrity additionally maps REQ-QML-008-AC02/AC03 to
`tests/test_cpp_overload_source_integrity.py::test_req_qml008_ac03_out_of_file_constructor_transport_cannot_bind`
and the exact containing-class/corrupt-file authority controls in that module.
The fourteen collected cases pass against the production binder. Source-size
authority does not turn incomplete SDK include evidence into type authority.

## Explicit emission observations

| Acceptance IDs | Exact ordinary tests | State |
| --- | --- | --- |
| REQ-QML-016-AC01 | `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_explicit_unknown_sites_do_not_admit_bare_calls`; `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_long_comment_crlf_bom_and_unicode_keep_original_spans`; `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_explicit_annotation_owns_emission_mechanism`; `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_override_cannot_recover_annotation_by_prefix`; `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_computed_receiver_keeps_full_explicit_source_site` | Local known/unknown/override/mechanism/original-byte source acceptance passes; computed receiver target remains unavailable. |
| REQ-QML-016-AC04 | `tests/test_qt_explicit_emissions.py::test_req_qml016_ac04_unknown_emissions_reload_as_owned_unresolved_sites`; `tests/test_qt_explicit_emission_updates.py::test_req_qml016_ac04_header_rename_remove_restore_and_marker_edits_preserve_observations`; `tests/test_qt_explicit_emission_updates.py::test_req_qml016_ac04_failed_explicit_refresh_retains_products_and_retries`; `tests/test_qt_explicit_emission_updates.py::test_req_qml016_ac04_readonly_declaration_removal_preserves_graph_and_explicit_retry` | Actual facade/build/reload/affected, cold/warm/manual/watch and real write-failure/repaired-repeat parity pass; Reviewed installed suite passes; final profile and limits appear below. |

## Project and header adoption

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-018-AC01 | `tests/test_qt_qmake_adoption.py::test_req_qml018_ac01_pwd_paths_preserve_current_file_and_original_token_spans`; `tests/test_qt_qmake_adoption.py::test_req_qml018_ac01_unrelated_conditional_build_settings_do_not_hide_module`; `tests/test_qt_qmake_adoption.py::test_req_qml018_ac01_relevant_conditions_remain_source_owned_uncertainty`; `tests/test_qt_qmake_adoption_integration.py::test_req_qml018_ac01_direct_facade_project_index_and_reload_preserve_pwd_roles`; `tests/test_qt_qmake_adoption_integration.py::test_req_qml018_ac01_metadata_only_pwd_edit_removal_matches_clean_updates` | Local reader/facade/project-index/reload/query and cold/warm/manual/watch pass. PWD is current-file literal evidence; import hints never extend discovery or configured roots. |
| REQ-QML-018-AC06 | `tests/test_qt_qmake_adoption.py::test_req_qml018_ac06_scope_depth_is_bounded`; `tests/test_qt_qmake_adoption.py::test_req_qml018_ac06_multibyte_path_transport_limit_is_explicit`; `tests/test_qt_qmake_adoption_integration.py::test_req_qml018_ac06_rejected_metadata_preserves_products_and_existing_cache`; `tests/test_qt_qmake_adoption_integration.py::test_req_qml018_ac06_readonly_publication_after_metadata_edit_retains_and_retries`; `tests/test_qt_header_updates.py::test_req_qml018_ac06_header_refresh_denial_preserves_then_recovers` | Local conditional/expansion/root escape, parser and actual read-only publication retention/repaired-repeat pass. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-018-AC07 | `tests/test_qt_header_adoption.py::test_req_qml018_ac07_whitespace_header_uses_cpp_source_authority`; `tests/test_qt_header_adoption.py::test_req_qml018_ac07_inert_cpp_markers_keep_c_dispatch`; `tests/test_qt_header_adoption.py::test_req_qml018_ac07_objective_c_retains_dispatch_priority`; `tests/test_qt_header_adoption.py::test_req_qml018_ac07_header_prefix_budget_and_digit_separators`; `tests/test_qt_header_updates.py::test_req_qml018_ac07_header_dispatch_mutation_matches_cold_and_warm` | Local lexical/plain-C/Objective-C/original-byte, bounded prefix and extractor-switch lifecycle pass. Header classification grants no native SDK authority. |

## Declared providers and reference callables

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-018-AC03 | `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_declared_expression_selects_backend_api`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_unknown_or_conflicting_factory_never_supplies_provider`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_conditional_provider_declaration_is_not_api_authority`; `tests/test_qt_declared_api_shapes.py::test_req_qml018_ac03_root_shape_must_match_literal_member_operator`; `tests/test_qt_declared_api_shapes.py::test_req_qml018_ac03_direct_producer_keeps_original_cv_shape_and_byte_position` | Exact source-owned API/shape/type/root evidence, malformed/unknown/conflicting/conditional/alias/operator rejection and no execution pass locally. |
| REQ-QML-018-AC04 | `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac04_context_service_subscriptions_have_distinct_sites`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac04_qml_lexical_and_property_shadows_precede_context_provider`; `tests/test_qt_typed_provider_consumers.py::test_req_qml018_ac04_typed_subscriptions_survive_build_reload_and_query`; `tests/test_qt_context_implicit_subscriptions.py::test_req_qml018_ac04_native_parameters_own_nested_provider_and_callback_lookup`; `tests/test_qt_context_implicit_subscriptions.py::test_req_qml018_ac04_nearer_local_callback_keeps_explicit_authority`; `tests/test_qt_declared_proof_integrity.py::test_req_qml018_ac04_ac06_reloaded_notify_proof_retains_mapping_identity` | Source subscription/handler identities, real NOTIFY, original scopes, explicit/local/implicit binding and default/directed reload pass; delivery is not a calls edge. Affected direction closes separately in INC-QML-30. |
| REQ-QML-018-AC05/AC06 | `tests/test_qt_typed_provider_updates.py::test_req_qml018_ac05_cpp_qml_metadata_and_signal_updates_match_clean_rebuild`; `tests/test_qt_typed_provider_updates.py::test_req_qml018_ac06_parser_and_resolver_failure_preserve_then_recover`; `tests/test_qt_declared_proof_integrity.py::test_req_qml018_ac06_typed_hop_rejects_altered_authoritative_declaration`; `tests/test_qt_declared_proof_integrity.py::test_req_qml018_ac06_typed_notify_revalidates_property_accessor_provenance` | Real source/configuration updates, cache/graph/cohort retention and repaired retry; independently corrupted canonical role/owner/file/span/type/accessor proof rejects. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-008-AC02/AC03; REQ-QML-018-AC02/AC03 | `tests/test_cpp_reference_returns.py::test_req_qml018_ac02_ac03_reference_return_has_canonical_callable`; `tests/test_cpp_reference_returns.py::test_req_qml018_ac02_qualified_reference_declaration_and_definition_keep_one_callable`; `tests/test_cpp_reference_returns.py::test_req_qml018_ac02_ac03_reference_provider_spans_and_consumers_survive_reload`; `tests/test_cpp_reference_returns.py::test_req_qml018_ac02_reference_fallback_requires_one_function_child` | Accepted grammar wrapper, ordinary controls, exact generic identity and original bytes; unsupported/missing/competing child authority rejects. Reference API profile preserves CV without runtime proof. |
| REQ-QML-011-AC01/AC04; REQ-QML-018-AC02/AC03/AC06 | `tests/test_cpp_reference_return_updates.py::test_req_qml018_ac02_ac03_reference_factory_edits_keep_identity_and_drop_stale_provider_edges`; `tests/test_cpp_reference_return_updates.py::test_req_qml018_ac02_ac03_reference_admission_failure_preserves_and_repairs`; `tests/test_cpp_reference_return_updates.py::test_req_qml018_ac02_ac03_readonly_reference_edit_retains_products_and_retries` | Actual C++-only manual/watch, cold/warm, stale-edge removal, parser/late publication/real Windows read-only failure, repaired idempotent retry pass locally. |

## Affected logical direction

Callback correspondence additionally assigns REQ-QML-018-AC04/AC06 to
`tests/test_qt_context_callback_integrity.py::test_req_qml018_ac04_ac06_callback_target_cannot_be_substituted`,
`tests/test_qt_context_callback_integrity.py::test_req_qml018_ac04_ac06_local_callback_precedes_same_named_qml_function`,
`tests/test_qt_context_callback_integrity.py::test_req_qml018_ac06_callback_borrowed_provenance_is_revalidated`
and `tests/test_qt_context_callback_integrity.py::test_req_qml018_ac04_callback_lookup_retains_object_scope`.
These exercise actual raw and default/directed build/JSON/reload, derived target
substitution, borrowed source/span/scope corruption and local/qualified controls.

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-018-AC04; REQ-QML-017-AC04; REQ-QML-011-AC01 | `tests/test_qt_affected_direction.py::test_native_provider_affected_uses_accepted_serialized_direction`; `tests/test_qt_affected_direction.py::test_logical_member_seed_finds_caller_without_reporting_seeded_method`; `tests/test_qt_affected_direction.py::test_legacy_edges_without_direction_keep_existing_traversal`; `tests/test_qt_affected_direction.py::test_logical_direction_depth_cycles_and_repeated_query_preserve_graph` | Local real build/JSON reload/CLI, directed/undirected insertion reversal, legacy, depth/filter/source-site and graph-preservation proof passes. |
| REQ-QML-018-AC06; REQ-QML-011-AC04 | `tests/test_qt_affected_direction.py::test_corrupt_direction_cannot_fall_back_to_physical_incoming`; `tests/test_qt_affected_direction.py::test_qt_owner_promotion_rejects_partial_or_foreign_direction`; `tests/test_qt_affected_direction.py::test_typed_reload_preserves_corrupt_dependency_direction_for_rejection`; `tests/test_qt_affected_direction.py::test_typed_reload_preserves_corrupt_owner_direction_for_rejection`; `tests/test_qt_affected_direction.py::test_boolean_marker_cannot_coerce_integer_endpoint_identity`; `tests/test_qt_affected_direction.py::test_parallel_edges_keep_valid_filtered_mechanism_after_invalid_direction` | Complete/partial/foreign/ill-typed/directed-contradictory corruption cannot authorize a dependency or source-owner link. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-018-AC04/AC06; REQ-QML-011-AC01/AC04 | `tests/test_qt_affected_direction_updates.py::test_native_affected_direction_cold_warm_update_removal_recovery_and_repeat` | Actual manual/watch source edits, removal, repair and cold/warm/repeated parity pass locally. |

## JSON direction integrity and combined adoption

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-013-AC01/AC03; REQ-QML-018-AC04/AC06 | `tests/test_qt_json_direction.py::test_json_direction_rejection_preserves_previous_bytes_and_safe_diagnostic`; `tests/test_qt_json_direction.py::test_json_directed_contradiction_rejects_before_first_file_exists`; `tests/test_qt_json_direction.py::test_native_source_proof_export_reload_consumer_survives_rejection_and_repair`; `tests/test_qt_json_direction.py::test_undirected_reversed_storage_retains_real_qml_dependency_direction` | Local real writer/native proof/reload/affected, force/rejection/prior-output/repair and accepted insertion reversal pass. |
| REQ-QML-013-AC01/AC03; REQ-QML-018-AC06 | `tests/test_qt_json_direction.py::test_external_direction_rejection_precedes_file_or_database_connection`; `tests/test_qt_json_direction.py::test_external_bidirectional_wrapper_honors_logical_pair_but_json_requires_native_direction`; `tests/test_qt_json_direction.py::test_legacy_unmarked_edges_and_valid_self_pairs_preserve_native_identity` | External preflight/call boundary and compatible logical wrapper behavior pass; no live database engine proof is claimed. |
| REQ-QML-011-AC04; REQ-QML-018-AC06 | `tests/test_qt_json_direction_updates.py::test_rejected_direction_clustered_publication_retains_products_cache_and_repairs` | Actual clustered manual/watch serializer rejection preserves seven durable products and real source-cache bytes; repair equals clean source contracts and repeat is byte-identical. |
| REQ-QML-018-AC01–AC05/AC07 | `tests/test_qt_combined_adoption.py::test_req_qml018_ac05_combined_configured_project_matches_cold_warm_and_updates` | Public combined CMake/qmake, whole root/safe application subroot, configured module, inherited emission/exact constructor/typed API/subscription, source cold/warm/manual/watch and QML-only callback edit parity pass locally. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-018-AC06 | `tests/test_qt_combined_adoption_safety.py::test_req_qml018_ac06_combined_rejection_retains_cache_products_and_retries`; `tests/test_qt_combined_adoption_safety.py::test_req_qml018_ac06_combined_readonly_destination_preserves_then_retries` | Missing parser, malformed source, unsafe import root and actual Windows read-only graph replacement retain prior products/cache and succeed on corrected retry/idempotent repeat. Reviewed installed suite passes; final profile and limits appear below. |

## First raw-update repeat

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-011-AC01; REQ-QML-018-AC05/AC06 | `tests/test_qt_initial_repeat.py::test_cold_combined_no_cluster_repeat_keeps_bytes_mtime_and_changed_source`; `tests/test_qt_initial_repeat.py::test_cold_generic_no_cluster_repeat_does_not_rewrite_first_graph` | Actual cold CLI/watch, CMake/qmake, whole-root/subroot, bytes/mtime repeat and subsequent real edit pass locally; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-011-AC01/AC04; REQ-QML-018-AC06 | `tests/test_qt_initial_repeat.py::test_known_absent_and_empty_run_lists_compare_equal_without_mutation`; `tests/test_qt_initial_repeat.py::test_nonempty_or_wrong_type_run_lists_remain_observable`; `tests/test_qt_initial_repeat.py::test_unknown_metadata_and_source_facts_still_compare_different`; `tests/test_qt_initial_repeat.py::test_real_raw_publication_failure_retains_prior_then_recovers` | Bounded normalization, unchanged input, meaningful/malformed/source proof controls and real staged replacement rejection/repair pass locally. |

## C++ file proof and candidate preflight

| Acceptance | Exact automated coverage | Current evidence |
| --- | --- | --- |
| REQ-QML-020-AC01/AC03; REQ-QML-008-AC02 | `tests/test_qt_cpp_file_roles.py::test_req_qml020_ac01_ac03_cpp_file_transport_retains_exact_file_identity`; `tests/test_qt_cpp_file_roles.py::test_req_qml008_ac02_cpp_file_role_preserves_separate_constructor_type_authority` | Current, legacy, incomplete, fresh and reloaded file proof; complete-record constructor authority stays separate. Local shared suite passes; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-020-AC02 | `tests/test_qt_cpp_file_roles.py::test_req_qml020_ac02_cpp_file_transport_cannot_authorize_corrupted_file_role`; `tests/test_qt_cpp_file_roles.py::test_req_qml020_ac02_cpp_file_joins_read_no_source_and_execute_no_corpus` | Actual borrowed transport at both joins rejects corruption without mutating, rereading or executing the corpus. Local shared suite passes; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-013-AC03; REQ-QML-011-AC04; REQ-QML-018-AC06 | `tests/test_qt_update_direction_integrity.py::test_actual_corrupt_candidate_refuses_shortcut_publication_and_repairs`; `tests/test_qt_update_direction_integrity.py::test_complete_reverse_pair_remains_accepted_on_undirected_storage` | 68 local manual/watch raw/clustered force/default failure/recovery/control cases pass; Reviewed installed suite passes; final profile and limits appear below. |

## Prior import and repeated event ownership

| Acceptance | Exact ordinary coverage | Evidence |
| --- | --- | --- |
| REQ-QML-020-AC03; REQ-QML-011-AC01/AC04 | `tests/test_qt_cpp_file_role_updates.py::test_req_qml020_ac03_cpp_transport_edits_and_removal_preserve_exact_membership`; `tests/test_qt_cpp_file_role_updates.py::test_req_qml011_ac04_cpp_deleted_import_keeps_still_referenced_external_endpoint`; `tests/test_qt_cpp_file_role_updates.py::test_req_qml011_ac04_cpp_import_cleanup_preserves_same_label_source_and_semantic_roles`; `tests/test_qt_cpp_file_role_updates.py::test_req_qml011_ac04_cpp_import_cleanup_requires_exact_prior_source_proof` | Manual/watch cold/warm deletion/restoration and exact raw prior-proof authority; source passes; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-018-AC06; REQ-QML-011-AC04 | `tests/test_qt_cpp_file_role_updates.py::test_req_qml018_ac06_cpp_orphan_cleanup_failed_publication_preserves_products_and_retries`; `tests/test_qt_cross_event_occurrences.py::test_req_qml018_ac06_cross_event_publication_failure_retains_prior_and_retries` | Actual Windows OS rejection, prior products and nonempty source cache retained, corrected retry/repeat pass; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-016-AC02/AC04; REQ-QML-017-AC02/AC04 | `tests/test_qt_cross_event_occurrences.py::test_req_qml016_ac02_ac04_cross_language_occurrences_keep_own_transport` | 1–16 mixed repeated connect/disconnect sites, both graph modes and QML/C++ directions, original span and bounded transport through production assembly/reload pass. |
| REQ-QML-011-AC03/AC04; REQ-QML-018-AC06 | `tests/test_qt_cross_event_occurrences.py::test_req_qml011_ac04_cross_event_edits_removal_and_repeat_match_clean`; `tests/test_qt_cross_event_occurrences.py::test_req_qml011_ac03_event_policy_refreshes_unchanged_source` | Actual C++/QML edits, stale removal, repair/full parity/unrelated Python and old-checkpoint refresh pass; Reviewed installed suite passes; final profile and limits appear below. |

## Bridge mechanisms and first minted provenance

| Acceptance | Exact ordinary coverage | Source result |
| --- | --- | --- |
| REQ-QML-018-AC04/AC06; REQ-QML-017-AC02/AC04; REQ-QML-010-AC03/AC04 | `tests/test_qt_bridge_mechanism_integrity.py::test_source_mechanisms_survive_builder_export_and_reload`; `tests/test_qt_bridge_mechanism_integrity.py::test_source_mechanism_substitution_is_rejected_before_graph_assembly`; `tests/test_qt_bridge_mechanism_integrity.py::test_context_access_revalidates_original_read_or_call`; `tests/test_qt_bridge_mechanism_integrity.py::test_endpoint_role_cannot_be_changed_to_repair_relation`; `tests/test_qt_bridge_mechanism_integrity.py::test_cross_language_flow_cannot_be_reversed_by_metadata`; `tests/test_qt_bridge_mechanism_integrity.py::test_reverse_reflection_repeats_original_supported_operation` | 166 new cases pass across 18 mechanisms; typed `uses` paths cannot bypass assembly proof. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-011-AC01/AC04; REQ-QML-018-AC05/AC06 | `tests/test_qt_publication_stub_origin.py::test_first_raw_stub_has_explicit_semantic_origin`; `tests/test_qt_publication_stub_origin.py::test_first_raw_import_repeat_preserves_bytes_mtime_and_genuine_edit`; `tests/test_qt_publication_stub_origin.py::test_existing_authored_endpoint_is_not_stamped_by_minting`; `tests/test_qt_publication_stub_origin.py::test_first_stamped_cpp_import_deletion_restoration_and_repeat`; `tests/test_qt_publication_stub_origin.py::test_new_stub_replacement_failure_retains_cohort_cache_then_retries` | 22 new cold manual/watch C++/Python, origin-preservation and injected replacement-failure/retry cases pass. Actual Windows denial is separately mapped above. Reviewed installed suite passes; final profile and limits appear below. |

## Final adoption delivery

Profile: Windows x64, Python 3.12.14, tree-sitter 0.25.2,
tree-sitter-language-pack 0.11.0; Qt 6 source inputs with CMake and qmake. The
reviewed tree is `9f0ae4ea75f47539df8ec8a66f1493b9e7f52b2f`. All 179 Python payloads
match the built wheel and installed package; the isolated installed selection
passes 3,024 tests with 36 historical optional/platform skips. None of the newly
added regression cases skips. Exact commands, digest and full-gate exceptions are
in [validation](../docs/qt-qml/VALIDATION.md#final-adoption-delivery).

| Criterion | Independently assigned production evidence | Current applicability and result |
| --- | --- | --- |
| REQ-QML-018-AC01 | Project/header table above: direct reader, facade, project index, reload and actual metadata-only updates; combined test and installed CMake/qmake whole/subroot CLI profiles | Locally Verified; arbitrary expansion/build execution excluded |
| REQ-QML-018-AC02 | Native syntax/cache upgrade and reference-return tables above: hand-checked original-byte facts, malformed/inert/generic controls and source/installed consumers | Locally Verified; unsupported relationships stay unresolved |
| REQ-QML-018-AC03 | `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_declared_expression_selects_backend_api`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_unknown_or_conflicting_factory_never_supplies_provider`; declaration-shape and producer-integrity modules mapped above, executed in source and installed selections | Locally Verified; accepted pointer/lvalue-reference declarations only, no factory execution or runtime conversion proof |
| REQ-QML-018-AC04 | `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac04_typed_service_call_and_property_are_source_owned`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac04_context_service_subscriptions_have_distinct_sites`; `tests/test_qt_typed_provider_consumers.py::test_req_qml018_ac04_typed_subscriptions_survive_build_reload_and_query`; affected direction, callback/mechanism proof and repeated-site tables above | Locally Verified in source and installed selections; no inferred runtime delivery |
| REQ-QML-018-AC05 | `tests/test_qt_combined_adoption.py::test_req_qml018_ac05_combined_configured_project_matches_cold_warm_and_updates`; `tests/test_qt_typed_provider_updates.py::test_req_qml018_ac05_cpp_qml_metadata_and_signal_updates_match_clean_rebuild`; four actual isolated installed CLI profiles, each initial/repeat exit 0 and identical graph bytes | Locally Verified; hand-checked CMake/qmake whole/subroot facts plus cold/warm/manual/watch mutation parity. Other hosted OS/Python cells unexecuted |
| REQ-QML-018-AC06 | Both combined safety tests above; `tests/test_qt_typed_provider_updates.py::test_req_qml018_ac06_parser_and_resolver_failure_preserve_then_recover`; JSON/preflight/repeat/orphan/publication failure tables above; actual Windows read-only denial complements injected replacement failure | Locally Verified in source and installed selections; prior products and nonempty successful cache, diagnostics, repair/repeat, no execution and bounded roots. Missing optional parser is separately exercised, not counted as a skip |
| REQ-QML-018-AC07 | Header-discovery/update table above: whitespace/BOM/CRLF/Unicode, comment/string/C/inconclusive/Objective-C controls and actual header edits; source and installed selections | Locally Verified; headers without accepted C++ evidence keep established dispatch |

INC-QML-11 inherited endpoints and INC-QML-15 exact constructor identity retain
their existing individual assignments above and pass in the reviewed installed
selection. The final full source command records 8,630 passed, 59 failed,
178 skipped and three warnings; the exact 59 failure identities equal baseline
5c0f2ca. Full Pyright has no added diagnostic identities but remains failed.
Current hosted platform jobs, live service delivery and native browser/device
procedure have not executed for this source. A global Verified or release-ready
status cannot be inferred from the bounded local evidence.
