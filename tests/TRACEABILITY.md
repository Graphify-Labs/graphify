# Qt/QML acceptance traceability

Current criterion IDs use `REQ-QML-`; completion increments use `INC-QML-`.
[Legacy aliases](../docs/qt-qml/IDENTIFIERS.md) retain earlier evidence identity.
Existing test filenames, function names and source annotations are unchanged.

INC-QML-00 through INC-QML-07 are complete for the documented bounded Qt 6/QML static
profile. Consumer, export, assistant, update and installed-artifact gates have
executed evidence. Final reviewed-head hosted proof is recorded separately in
[VALIDATION.md](../docs/qt-qml/VALIDATION.md) and the delivery PR.
The initial profile retains seventeen requirements and sixty-eight independently
testable criteria in the canonical [requirements](../docs/REQUIREMENTS.md).
REQ-QML-018 adds six adoption criteria, for eighteen requirements and seventy-four
criteria overall. AC02 has local verification for bounded native syntax cases;
the remaining adoption criteria are unverified. Explicit gaps appear below.
REQ-QML-019 adds four community-view criteria, bringing the catalog to nineteen
requirements and seventy-eight criteria. INC-QML-10 revalidates the existing
native ownership criteria for complete bodies and canonical definition provenance;
multi-level inherited endpoint lookup remains an explicit INC-QML-11 gap.
REQ-QML-020 adds three planned membership-projection criteria, for twenty
requirements and eighty-one criteria. INC-QML-12/13 source and final installed
public-fixture regressions below do not verify that planned projection or the
broader adoption gaps.
Verified local profile means
executed source/consumer acceptance, not runtime equivalence. Every declared
platform lane requires its own installed-artifact evidence; a skip is not a pass.
See [implementation limits](../docs/qt-qml/IMPLEMENTATION.md),
[export contracts](../docs/qt-qml/EXPORT_MATRIX.md) and
[platform matrix](../docs/qt-qml/PLATFORM_MATRIX.md).

## Individual acceptance assignments

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
| REQ-QML-008-AC01 | `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints` | INC-QML-05 | Verified static source profile |
| REQ-QML-008-AC02 | `tests/test_qt_cpp_exposure.py::test_header_implementation_members_reuse_accepted_canonical_ids`; `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints`; `tests/test_qt_cpp_definition_ownership.py::test_req_qml008_ac02_definition_provenance_keeps_emission_owned_through_aggregate`; normalization, conflicting callable/body, missing completeness, external/local class, generic identity and original-byte controls in that module; `tests/test_qt_cpp_owner_upgrade.py::test_qml008_ac02_policy_three_reparses_unchanged_native_ownership` (update/extract); [current constructor/source-containment assignments](#constructor-and-source-containment-corrections) | INC-QML-05; INC-QML-10/12/13 corrections | Locally verified bounded complete-body, constructor and source-containment corrections; unsupported overload/adoption gaps retained |
| REQ-QML-008-AC03 | `tests/test_qt_native_project_integration.py::test_cpp_source_in_two_distinct_build_contexts_has_no_arbitrary_native_provider; tests/test_qt_qml_integration.py::test_ambiguous_overload_and_version_revised_member_are_explicit` | INC-QML-05 | Verified static source profile |
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
| REQ-QML-016-AC01 | `tests/test_qt_cpp_syntax.py::test_access_sections_keep_original_roles_offsets`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls`; `tests/test_qt_signals_slots.py::test_macro_sections_private_meta_slots_and_comments`; `tests/test_qt_cpp_definition_ownership.py::test_req_qml016_ac01_forward_declaration_does_not_compete_with_complete_definition` | INC-QML-04b; INC-QML-10 correction | Locally verified bounded ownership correction; grandparent endpoint lookup remains unverified (INC-QML-11) |
| REQ-QML-016-AC02 | `tests/test_qt_signals_slots.py::test_overloads_need_selector_and_dynamic_sender_stays_unresolved`; `tests/test_qt_events_boundaries.py::test_functor_function_and_connection_handle_disconnect`; `tests/test_qt_events_boundaries.py::test_explicit_cast_signal_to_signal_and_condition_flags`; `tests/test_qt_events_boundaries.py::test_private_typed_pointer_and_incompatible_receiver_are_rejected` | INC-QML-04b | Verified (native source profile) |
| REQ-QML-016-AC03 | `tests/test_qt_events_boundaries.py::test_explicit_cast_signal_to_signal_and_condition_flags`; `tests/test_qt_events_boundaries.py::test_computed_signal_receiver_and_custom_connect_are_not_qt_targets`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls` | INC-QML-04b | Verified (native source profile) |
| REQ-QML-016-AC04 | `tests/test_qt_event_incremental_consumers.py::test_qml016_ac04_event_mutation_and_removal_match_clean_rebuild_without_delivery_calls`; `tests/test_qt_html_consumers.py::test_signal_emission_is_not_rendered_as_a_caller_in_the_call_table`; `tests/test_qt_affected_definitions.py`; `tests/test_qt_mcp_consumers.py::test_qml016_ac04_http_metadata_search_keeps_connection_reference_semantics`; `tests/test_qt_worker_cache_integrity.py`; `tests/test_qt_cpp_owner_upgrade.py::test_qml016_ac04_failed_owner_upgrade_retains_prior_graph_stamp_and_manifest` (force off/on); persisted JSON and aggregate ownership in `tests/test_qt_cpp_definition_ownership.py` | INC-QML-07; INC-QML-10 correction | Locally verified correction/upgrade/retention; multi-level inherited endpoint parity remains unverified (INC-QML-11) |
| REQ-QML-017-AC01 | `tests/test_qt_project_admission.py::test_qml017_ac01_literal_module_load_reaches_declared_component_and_property; tests/test_qt_project_admission.py::test_qml009_ac03_public_metadata_qrc_load_build_export_reload` | INC-QML-05 | Verified static source profile |
| REQ-QML-017-AC02 | `tests/test_qml_cpp_access.py::test_view_root_and_literal_object_name_property_access`; `tests/test_qt_access_providers.py::test_qqmlproperty_read_write_preserves_property_handle`; `tests/test_qt_project_admission.py::test_qml017_ac01_literal_module_load_reaches_declared_component_and_property`; `tests/test_qt_cpp_definition_ownership.py::test_req_qml017_ac02_namespace_definition_owns_source_backed_qml_access` | INC-QML-05; INC-QML-10 correction | Locally verified bounded canonical-definition access ownership |
| REQ-QML-017-AC03 | `tests/test_qt_access_providers.py`; `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints`; `tests/test_qt_native_project_integration.py` | INC-QML-05 | Verified (bounded static profile) |
| REQ-QML-017-AC04 | `tests/test_qt_final_incremental_parity.py::test_qml017_ac04_qml_member_edit_refreshes_unchanged_reverse_cpp_access`; `tests/test_qml_cpp_access.py::test_duplicate_object_names_do_not_select_first_child`; `tests/test_qt_access_providers.py::test_duplicate_context_provider_and_local_shadow_do_not_choose`; `tests/test_qt_metadata_incremental.py`; `tests/test_qt_qml_export_consumers.py`; `tests/test_qt_mcp_stdio.py`; persisted export ownership in `tests/test_qt_cpp_definition_ownership.py::test_req_qml017_ac02_namespace_definition_owns_source_backed_qml_access` | INC-QML-07; INC-QML-10 correction | Locally verified bounded persisted access ownership; adoption provider gaps retained |

## Native ownership correction and remaining gaps

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

INC-QML-11 remains unverified and must reproduce and correct grandparent
inherited-signal endpoint lookup under
REQ-QML-016-AC01/AC04; recursive class compatibility currently coexists with an
immediate-base-only member fallback. INC-QML-12/13 now have bounded source
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
| REQ-QML-008-AC02 | `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_constructor_prototypes_are_callable_methods`; `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_constructor_definition_retains_id_and_exact_accepted_owner`; `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_constructor_join_rejects_foreign_or_corrupt_accepted_proof`; `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_corrupted_owner_cannot_relabel_another_actual_constructor`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_plain_member_uses_exact_callable_without_native_class_claim`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_local_class_links_to_enclosing_callable_without_type_authority`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_source_fallback_rejects_unproved_or_noncallable_context`; `tests/test_qt_source_file_containment.py::test_req_qml008_ac02_unknown_native_owner_keeps_actual_file_context_after_reload`; `tests/test_qt_source_file_containment.py::test_req_qml008_ac02_file_context_requires_unique_actual_file_role` | Generic direct/facade constructor identity, accepted callable containment and accepted file containment. Missing, foreign, duplicate, non-callable/non-AST and unmarked borrowed inputs cannot prove ownership. Current focused/source/artifact and installed public-fixture evidence pass within the bounded profile. |
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

Owner: Qt/QML integration maintainer. INC-QML-08 assigns disjoint reader, native
declaration and context-resolution owners before implementation; its integration
owner accepts the production and installed-artifact handoff. Each row distinguishes
executed local proof from remaining metadata, provider/service and combined
adoption gaps. Native-header classification is a separate planned discovery
assessment; it is not evidence for the bounded native syntax criterion.
The [INC-QML-08 plan](../docs/qt-qml/PLAN.md#inc-qml-08--installed-project-adoption-hardening)
defines the proposed public synthetic profile and completion gates. Original
REQ-QML-001–REQ-QML-017 evidence above applies to the original bounded profile only.

| Criterion | Evidence or exact remaining gap | Completion increment | Status |
| --- | --- | --- | --- |
| REQ-QML-018-AC01 | Gap: public qmake fixture and production reader/facade assertions for bounded `$$PWD`, build-statement relevance, conditional facts, import-hint roles, original spans and rejected expansion; no new acceptance command executed | INC-QML-08a | Planned / Not executed |
| REQ-QML-018-AC02 | `tests/test_qt_cpp_adoption_syntax.py::test_req_qml018_ac02_empty_parameter_default_recovers_exact_declared_member`; `tests/test_qt_cpp_adoption_syntax.py::test_req_qml018_ac02_unused_arguments_keep_evaluated_nested_calls`; `tests/test_qt_cpp_adoption_syntax.py::test_req_qml018_ac02_bom_unicode_crlf_preserve_original_member_and_call_offsets`; `tests/test_qt_cpp_adoption_syntax.py::test_req_qml018_ac02_numeric_separator_keeps_later_signal_ownership`; `tests/test_qt_cpp_adoption_syntax.py::test_req_qml018_ac02_malformed_numeric_separators_remain_rejected`; malformed/inert/generic controls in the same module; `tests/test_qt_cpp_upgrade_invalidation.py::test_req_qml018_ac02_schema_retires_real_same_package_syntax_cache`; `tests/test_qt_cpp_upgrade_invalidation.py::test_req_qml018_ac02_policy_epoch_refreshes_same_package_unchanged_cpp`; `tests/test_qt_cpp_upgrade_invalidation.py::test_req_qml018_ac02_unrelated_plain_cpp_retains_actual_warm_cache`; focused source run: 63 passed; upgrade module: 13 passed; broad source run: 716 passed/7 skips. Reviewed installed-wheel identity and remaining profile limits: [validation](../docs/qt-qml/VALIDATION.md#inc-qml-08a-native-source-compatibility) | INC-QML-08a | Locally verified (bounded native syntax/upgrade); wider adoption not verified |
| REQ-QML-018-AC03 | Gap: canonical typed factory/member context-provider fixtures plus unknown/conflicting/conditional ownership controls; production provider resolution and no-execution assertions not implemented | INC-QML-08b | Planned / Not executed |
| REQ-QML-018-AC04 | Gap: exposed-provider/child-service calls, `Connections` and `signal.connect(handler)` subscriptions with shadowing/ambiguity controls, persisted consumer assertions and no-delivery-call checks | INC-QML-08b | Planned / Not executed |
| REQ-QML-018-AC05 | Gap: built/installed optional-wheel CLI proof at whole-project and configured safe subroot, source parity, metadata/provider/member/signal mutation cold/warm/manual/watch matrix and affected compatibility lanes | INC-QML-08c | Planned / Not executed |
| REQ-QML-018-AC06 | Native-slice proof: `tests/test_qt_cpp_upgrade_invalidation.py::test_req_qml018_ac02_current_epoch_failure_keeps_real_cache_and_products`; `tests/test_qt_cpp_upgrade_invalidation.py::test_req_qml018_ac02_actual_cli_refreshes_old_epoch_without_source_or_package_change`. Remaining gap: the combined adoption profile's forced resolver/write failures, corrected retry/idempotency, parser-absence, root/corruption, bounded diagnostic and privacy controls | INC-QML-08c; safety applies in 08a/08b | Partially evidenced (native upgrade/retention); combined profile not executed |

## HTML community-view criteria

REQ-QML-019 is locally verified at the Python exporter/CLI and emitted JavaScript
selection boundaries. Node harnesses execute production scripts with the external
vis network isolated; they prove dataset admission, controls and source payload,
not a new browser-engine or visual acceptance run. Installed-artifact identity and
executed commands are recorded in VALIDATION.md.

| Criterion | Exact production evidence | Increment | Status |
| --- | --- | --- | --- |
| REQ-QML-019-AC01 | `tests/test_html_community_recovery.py::test_req_qml019_ac01_large_export_recovers_complete_partition`; `tests/test_html_community_recovery.py::test_req_qml019_ac01_invalid_saved_membership_is_rebuilt_without_stale_names`; `tests/test_html_community_recovery.py::test_req_qml019_ac01_cli_exports_unclustered_saved_graph_without_sidecars`; `tests/test_html_community_recovery.py::test_req_qml019_ac01_explicit_graph_uses_adjacent_analysis_not_malformed_cwd_sidecar` | INC-QML-09 | Locally verified |
| REQ-QML-019-AC02 | `tests/test_html_community_recovery.py::test_req_qml019_ac02_existing_groups_get_missing_labels`; small/empty/authoritative group and name cases in the same module; `tests/test_qt_graph_html_payload.py::test_qml013_ac03_aggregated_html_explicitly_states_source_fact_omission`; existing escaping and written-node-info runtime regressions in `tests/test_export.py`; [current exact community-count assignments](#constructor-and-source-containment-corrections) | INC-QML-09; INC-QML-13 correction | Locally verified exporter/emitted-script counts and reviewed installed artifact; browser visual inspection is separate |
| REQ-QML-019-AC03 | `tests/test_html_community_recovery.py::test_req_qml019_ac03_invalid_computed_partition_preserves_output_and_recovers`; `tests/test_html_community_recovery.py::test_req_qml019_ac03_cli_unavailable_view_retains_prior_outputs_and_retries`; `tests/test_html_community_recovery.py::test_req_qml019_ac03_cli_failure_has_no_false_write_and_preserves_prior_html`; `tests/test_html_community_recovery.py::test_req_qml019_ac03_isolate_partition_over_hard_cap_is_not_published` | INC-QML-09 | Locally verified; actual atomic replacement failure injected at its OS boundary |
| REQ-QML-019-AC04 | `tests/test_html_initial_view.py::test_default_select_all_constructs_every_exported_node_and_edge_before_network`; `tests/test_html_initial_view.py::test_optional_overview_selects_only_ten_largest_source_communities`; `tests/test_html_initial_view.py::test_optional_overview_ties_use_numeric_community_ids_independent_of_insertion`; `tests/test_html_initial_view.py::test_optional_overview_filters_all_none_and_reset_update_real_datasets`; `tests/test_html_initial_view.py::test_optional_overview_search_reveals_deferred_group_with_exact_source_metadata`; grouped/ungrouped/partial startup controls in the same module | INC-QML-09 | Locally verified checked startup through production emitted-script harness; installed artifact checked. Prior unchecked-startup evidence is revision-specific; camera/layout appearance not reverified |

## Planned project-membership projection

Owner: Qt project-metadata integration maintainer. INC-QML-14 owns all three
REQ-QML-020 criteria. Current source/resource lookup, source-file containment and
community edge counts do not constitute declaration-to-file/component membership
projection. No automated implementation test or installed proof is assigned yet.

| Criterion | Exact remaining production gap | Completion increment | Status |
| --- | --- | --- | --- |
| REQ-QML-020-AC01 | Public literal CMake/qmake/source and qrc-alias fixtures must prove uniquely accepted endpoints, direction, context, original spans and confidence through facade/build/JSON reload/scoped query, with existing loader/module lookup unchanged. | INC-QML-14 | Planned / Not executed |
| REQ-QML-020-AC02 | Missing/duplicate/conditional/generated/out-of-root targets and same-name scopes need explicit unresolved coverage without guessed edges, new reads or execution; actual malformed/failed joins must retain existing diagnostics and prior durable products. | INC-QML-14 | Planned / Not executed |
| REQ-QML-020-AC03 | Source/resource edit, rename, deletion and ambiguity must remove stale edges; cold/warm/manual/watch and no-change parity, stable unrelated facts, persisted HTML membership and actual failure/retry tests remain unexecuted. | INC-QML-14 | Planned / Not executed |
