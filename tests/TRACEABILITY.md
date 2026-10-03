# Qt/QML acceptance traceability

QML-00 through QML-03 are implemented for the optional Windows x64 static profile.
The canonical [requirements](../docs/REQUIREMENTS.md) retain seventeen requirements
and sixty-eight criteria. Each row keeps its completion increment and independently
testable case. Verified means the documented source-analysis profile passes;
it does not establish Qt runtime equivalence or later C++/metadata/consumer support.
See [executed evidence](../docs/qt-qml/VALIDATION.md) and
[implementation limits](../docs/qt-qml/IMPLEMENTATION.md) for commands, platforms,
skips, baseline failures and exact packaging provenance.

All QML source/artifact tests: 247 passed, two Windows symlink-permission skips
in each of the four Python lanes, including the final BOM/CRLF reader regressions.
QML-001/003/004/005/006/007 pass their four criteria in the declared profile.
QML-002/010/011/012/013/014/015 have passing QML cases with remaining whole-Qt gates;
QML-008/016/017 have native source evidence; build/resource and final consumer
gates remain open. Minimal qmldir support is partial QML-009.
The optional/core wheel checks pass on Windows Python 3.10/3.12/3.13/3.14 and core
Python 3.12. QML-03 hosted Ubuntu full suites and all twelve optional/core wheel lanes pass;
see VALIDATION.md for reviewed source and tested merge SHAs. No skip counts as a pass.

## Individual acceptance assignments

Tests named with `::` below exist and were executed. Rows without exact delivered
evidence retain their assigned case as an explicit gap. Partial evidence does not
close the full criterion, especially C++ changes, metadata types and all consumers.
Later increments reverify affected evidence; preserve these identifiers.

| Acceptance ID | Actual evidence / assigned open case | Planned completion increment | Status |
| --- | --- | --- | --- |
| QML-001-AC01 | `tests/test_qml_wheel_artifact.py::test_qml001_ac01_built_wheel_contains_adapter_and_optional_extra_metadata`; `tests/test_qml_wheel_artifact.py::test_qml001_ac01_ac03_built_artifact_production_import_and_parser_boundary` | QML-01 | Verified (declared profile) |
| QML-001-AC02 | `tests/test_qml_syntax_profile.py::test_qml001_ac02_handchecked_profile_uses_production_extractor_and_original_spans`; `tests/test_qml_syntax_profile.py::test_qml001_ac02_profile_runs_offline_in_fresh_production_process_without_corpus_execution` | QML-03 | Verified (declared profile) |
| QML-001-AC03 | `tests/test_qml_failures.py::test_qml001_ac03_missing_optional_import_is_safe_and_does_not_break_python`; `tests/test_qml_failures.py::test_qml001_ac03_incompatible_parser_load_is_bounded_failure` | QML-01 | Verified (declared profile) |
| QML-001-AC04 | `tests/test_qml_declarations.py::test_qml001_ac04_empty_source_is_distinguishable_from_parse_failure`; `tests/test_qml_declarations.py::test_qml012_ac01_malformed_or_partial_parse_has_no_authoritative_nodes`; `tests/test_qml_failures.py::test_qml001_ac04_unsupported_annotated_root_is_not_file_only_success` | QML-01 | Verified (declared profile) |
| QML-002-AC01 | `tests/test_qt_config_incremental.py::test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider; tests/test_qml_identity.py::test_qml01_ui_suffix_names_component_without_losing_filename_identity` | QML-06 | Verified static source profile |
| QML-002-AC02 | `tests/test_qt_metadata_admission.py::test_cmake_exact_name_does_not_reclassify_arbitrary_text; tests/test_qml_integration.py::test_qml002_ac02_named_qmldir_dispatch_directory_and_single_file_root` | QML-06 | Verified static source profile |
| QML-002-AC03 | `tests/test_qt_metadata_admission.py::test_qt_metadata_discovery_obeys_existing_ignore_policy; tests/test_qt_resource_resolution.py::test_qrc_host_reads_entities_traversal_and_malformed_xml_rejected` | QML-06 | Verified static source profile |
| QML-002-AC04 | `tests/test_qml_identity.py::test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts; tests/test_qt_config_incremental.py::test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider` | QML-06 | Verified static source profile |
| QML-003-AC01 | `tests/test_qml_declarations.py::test_qml003_ac01_exact_declarations_ownership_and_raw_types`; `tests/test_qml_declarations.py::test_qml003_ac01_unicode_crlf_spans_and_original_names`; `tests/test_qml_syntax_profile.py::test_qml003_ac01_property_binding_and_array_objects_keep_exact_owners` | QML-01 | Verified (declared profile) |
| QML-003-AC02 | `tests/test_qml_identity.py::test_qml003_ac02_duplicate_basename_uses_full_relative_path`; `tests/test_qml_identity.py::test_qml003_ac02_inline_component_equal_ids_and_members_have_separate_owners`; `tests/test_qml_graph.py::test_qml003_ac02_same_stem_cpp_js_and_qml_do_not_merge`; template barrier cases in test_qml_syntax_profile.py | QML-01 | Verified (declared profile) |
| QML-003-AC03 | `tests/test_qml_declarations.py::test_qml003_ac03_comments_literals_groups_and_js_inner_functions_are_not_objects` | QML-01 | Verified (declared profile) |
| QML-003-AC04 | `tests/test_qml_identity.py::test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts`; `tests/test_qml_identity.py::test_qml003_ac04_comment_insert_changes_spans_but_not_named_identity`; `tests/test_qml_integration.py::test_qml010_ac01_real_process_pool_and_warm_order_match_sequential` | QML-01 | Verified (declared profile) |
| QML-004-AC01 | `tests/test_qml_resolution.py::test_aliased_directory_and_uri_imports_do_not_cross_bind`; `tests/test_qml_resolution.py::test_version_availability_and_latest_compatible_export` | QML-02 | Verified (declared profile) |
| QML-004-AC02 | `tests/test_qml_resolution.py::test_aliased_directory_and_uri_imports_do_not_cross_bind`; `tests/test_qml_resolution.py::test_versioned_layout_and_missing_version_evidence` | QML-02 | Verified (declared profile) |
| QML-004-AC03 | `tests/test_qml_resolution.py::test_competing_providers_and_missing_modules_have_no_target_edges` | QML-02 | Verified (declared profile) |
| QML-004-AC04 | `tests/test_qml_resolution.py::test_declared_roots_and_remote_import_never_expand_corpus`; `tests/test_qml_resolution.py::test_directory_and_script_projection_and_ignored_disk_provider` | QML-02 | Verified (declared profile) |
| QML-005-AC01 | `tests/test_qml_scope.py::test_component_ids_do_not_leak_between_files_or_inline_components` | QML-02 | Verified (declared profile) |
| QML-005-AC02 | `tests/test_qml_scope.py::test_inline_shadow_and_inherited_members_are_distinct_roles`; `tests/test_qml_scope.py::test_singleton_pragma_and_qualified_access` | QML-02 | Verified (declared profile) |
| QML-005-AC03 | `tests/test_qml_scope.py::test_internal_external_dynamic_and_lexical_members_stay_unresolved` | QML-02 | Verified (declared profile) |
| QML-005-AC04 | `tests/test_qml_resolution.py::test_module_script_exports_have_separate_lookup_roles` | QML-02 | Verified (declared profile) |
| QML-006-AC01 | `tests/test_qml_expressions.py::test_binding_reads_and_nested_qualified_aliases` | QML-03 | Verified (declared profile) |
| QML-006-AC02 | `tests/test_qml_expressions.py::test_alias_cycles_missing_and_ambiguous_targets_never_guess`; `tests/test_qml_expressions.py::test_component_and_object_scope_do_not_bind_hidden_identifiers` | QML-03 | Verified (declared profile) |
| QML-006-AC03 | `tests/test_qml_expressions.py::test_dynamic_reads_and_executable_source_are_only_analyzed` | QML-03 | Verified (declared profile) |
| QML-006-AC04 | `tests/test_qml_expressions.py::test_repeated_sites_survive_actual_directed_build_and_json`; `tests/test_qml_integration.py::test_qml010_ac02_default_undirected_export_reload_keeps_qml_direction` | QML-03 | Verified (declared profile) |
| QML-007-AC01 | `tests/test_qml_handlers.py::test_parameters_block_bindings_nested_functions_and_computed_calls`; `tests/test_qml_handlers.py::test_inherited_and_alias_target_signal_parameters_shadow_properties` | QML-03 | Verified (declared profile) |
| QML-007-AC02 | `tests/test_qml_scripts.py::test_literal_imported_helpers_and_library_do_not_inherit_document_ids`; `tests/test_qml_scripts.py::test_mjs_explicit_exports_aliases_and_private_functions`; `tests/test_qml_scripts.py::test_accepted_script_dependencies_support_classic_and_esm_imports`; `tests/test_qml_scripts.py::test_script_overlay_retains_original_shared_js_nodes_and_never_executes` | QML-03 | Verified (declared profile) |
| QML-007-AC03 | `tests/test_qml_handlers.py::test_declared_and_property_change_handlers_are_subscriptions`; `tests/test_qml_handlers.py::test_connections_target_and_dynamic_target_stay_distinct`; `tests/test_qml_adversarial.py::test_mixed_legacy_connections_handlers_do_not_activate_ignored_function_handlers` | QML-03 | Verified (declared profile) |
| QML-007-AC04 | `tests/test_qml_scripts.py::test_generic_js_calls_cannot_bind_to_qml_owned_expression_sites`; `tests/test_qml_scripts.py::test_script_overlay_does_not_read_unaccepted_imports_or_network` | QML-03 | Verified (declared profile) |
| QML-008-AC01 | `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints` | QML-05 | Verified static source profile |
| QML-008-AC02 | `tests/test_qt_cpp_exposure.py::test_header_implementation_members_reuse_accepted_canonical_ids; tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints` | QML-05 | Verified static source profile |
| QML-008-AC03 | `tests/test_qt_native_project_integration.py::test_cpp_source_in_two_distinct_build_contexts_has_no_arbitrary_native_provider; tests/test_qt_qml_integration.py::test_ambiguous_overload_and_version_revised_member_are_explicit` | QML-05 | Verified static source profile |
| QML-008-AC04 | `tests/test_qt_cpp_syntax.py::test_unicode_crlf_macro_spans_are_original_bytes; tests/test_qt_cpp_syntax.py::test_comments_strings_raw_literals_and_preprocessor_definitions_are_inert` | QML-05 | Verified static source profile |
| QML-009-AC01 | `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints; tests/test_qt_resource_resolution.py::test_public_qt6_cmake_and_qmake_fixtures_describe_identical_membership` | QML-05 | Verified static source profile |
| QML-009-AC02 | `tests/test_qml_types_metadata.py::test_qmltypes_members_flags_exports_original_byte_provenance; tests/test_qml_types_metadata.py::test_qmltypes_cpp_member_conflict_preserves_authoritative_source` | QML-05 | Verified static source profile |
| QML-009-AC03 | `tests/test_qt_project_admission.py::test_qml009_ac03_public_metadata_qrc_load_build_export_reload; tests/test_qt_resource_resolution.py::test_qrc_host_reads_entities_traversal_and_malformed_xml_rejected` | QML-05 | Verified static source profile |
| QML-009-AC04 | `tests/test_qt_project_metadata.py::test_cmake_conditional_and_expanded_metadata_is_not_authoritative; tests/test_qt_project_metadata.py::test_qmake_conditions_expansion_functions_never_produce_guessed_context` | QML-05 | Verified static source profile |
| QML-010-AC01 | `tests/test_qml_integration.py::test_qml010_ac01_real_process_pool_and_warm_order_match_sequential`; open completion: Ordering/cache/process determinism and normalized-name collisions | QML-07 | Partial; later gate open |
| QML-010-AC02 | `tests/test_qml_integration.py::test_qml010_ac02_default_undirected_export_reload_keeps_qml_direction`; `tests/test_qml_integration.py::test_qml010_ac02_literal_script_import_keeps_generic_file_endpoint_after_build_reload`; open completion: Endpoint, source-span and canonical-path JSON remapping | QML-07 | Partial; later gate open |
| QML-010-AC03 | `tests/test_qml_expressions.py::test_repeated_sites_survive_actual_directed_build_and_json`; open completion: Multiple promised facts survive simple-graph projection | QML-07 | Partial; later gate open |
| QML-010-AC04 | `tests/test_qml_resolution.py::test_projection_graph_build_export_reload_preserves_all_site_roles`; open completion: Confidence/evidence distinctions and source-backed provenance priority | QML-07 | Partial; later gate open |
| QML-011-AC01 | `tests/test_qt_metadata_incremental.py::test_native_cpp_provider_only_edit_refreshes_unchanged_qml_and_warm_overlay` | QML-06 | Verified static source profile |
| QML-011-AC02 | `tests/test_qt_metadata_incremental.py::test_build_provider_only_mutations_equal_clean_accepted_corpus; tests/test_qt_metadata_incremental.py::test_resource_only_mutations_refresh_unchanged_cpp_loaders; tests/test_qt_config_incremental.py::test_qml011_ac02_last_qt_source_deletion_cleans_facts_and_commits_nonqt_state` | QML-06 | Verified static source profile |
| QML-011-AC03 | `tests/test_qt_config_incremental.py::test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider; tests/test_qt_config_incremental.py::test_qml011_ac03_package_version_change_reanalyzes_unchanged_corpus` | QML-06 | Verified static source profile |
| QML-011-AC04 | `tests/test_qt_config_incremental.py::test_qml012_ac02_malformed_new_source_preserves_graph_manifest_and_stamp; tests/test_qt_config_incremental.py::test_qml012_ac02_invalid_import_configuration_preserves_prior_stamp` | QML-06 | Verified static source profile |
| QML-012-AC01 | `tests/test_qml_resolver_safety.py::test_native_join_failure_is_guarded_and_successful_retry_is_clean`; open completion: Bounded parser/extractor/resolver failure diagnostics | QML-06 | Partial; later gate open |
| QML-012-AC02 | Open case: Existing valid graph/cache preservation on failed extraction | QML-06 | Gap: completion case pending |
| QML-012-AC03 | Open case: Intentional deletion versus failure and persistence guards | QML-06 | Gap: completion case pending |
| QML-012-AC04 | `tests/test_qml_failures.py::test_qml012_ac04_unreadable_or_oversized_source_has_safe_failure`; `tests/test_qml_failures.py::test_qml012_ac04_deep_source_terminates_at_supported_bound`; open completion: Hostile input resource bounds, redaction and nonexecution | QML-06 | Partial; later gate open |
| QML-013-AC01 | Open case: Query/explain/path scopes, routes and source evidence | QML-07 | Gap: completion case pending |
| QML-013-AC02 | Open case: Affected traversal dependency direction and included consumers | QML-07 | Gap: completion case pending |
| QML-013-AC03 | `tests/test_qml_integration.py::test_qml010_ac02_default_undirected_export_reload_keeps_qml_direction`; open completion: Advertised export/reload preservation and explicit omissions | QML-07 | Partial; later gate open |
| QML-013-AC04 | Open case: MCP/CLI parity and deliberate metadata search indexing | QML-07 | Gap: completion case pending |
| QML-014-AC01 | `tests/test_qml_wheel_artifact.py::test_qml001_ac01_built_wheel_contains_adapter_and_optional_extra_metadata`; open completion: Every advertised host/Python lane install and extraction evidence | QML-07 | Partial; later gate open |
| QML-014-AC02 | `tests/test_qml_identity.py::test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts`; open completion: Windows/POSIX path/Unicode/relocation and optional-parser parity | QML-07 | Partial; later gate open |
| QML-014-AC03 | Open case: Relevant existing-language and shared-boundary regression comparison | QML-07 | Gap: completion case pending |
| QML-014-AC04 | Open case: Honest skipped/unrun/baseline/type-check accounting | QML-07 | Gap: completion case pending |
| QML-015-AC01 | Open case: PR requirement/acceptance/support documentation consistency | QML-07 | Gap: completion case pending |
| QML-015-AC02 | Open case: Authoritative skillgen changes and artifact/schema checks | QML-07 | Gap: completion case pending |
| QML-015-AC03 | Open case: Reviewed base/head, dependency attribution and PR reuse evidence | QML-07 | Gap: completion case pending |
| QML-015-AC04 | Open case: Every release promise traced to evidence or explicit deferral; privacy scan | QML-07 | Gap: completion case pending |
| QML-016-AC01 | `tests/test_qt_cpp_syntax.py::test_access_sections_keep_original_roles_offsets`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls`; `tests/test_qt_signals_slots.py::test_macro_sections_private_meta_slots_and_comments` | QML-04b | Verified (native source profile) |
| QML-016-AC02 | `tests/test_qt_signals_slots.py::test_overloads_need_selector_and_dynamic_sender_stays_unresolved`; `tests/test_qt_events_boundaries.py::test_functor_function_and_connection_handle_disconnect`; `tests/test_qt_events_boundaries.py::test_explicit_cast_signal_to_signal_and_condition_flags`; `tests/test_qt_events_boundaries.py::test_private_typed_pointer_and_incompatible_receiver_are_rejected` | QML-04b | Verified (native source profile) |
| QML-016-AC03 | `tests/test_qt_events_boundaries.py::test_explicit_cast_signal_to_signal_and_condition_flags`; `tests/test_qt_events_boundaries.py::test_computed_signal_receiver_and_custom_connect_are_not_qt_targets`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls` | QML-04b | Verified (native source profile) |
| QML-016-AC04 | Open case: Call/emission/connect/disconnect distinction, consumer and update preservation | QML-07 | Gap: planned |
| QML-017-AC01 | `tests/test_qt_project_admission.py::test_qml017_ac01_literal_module_load_reaches_declared_component_and_property; tests/test_qt_project_admission.py::test_qml009_ac03_public_metadata_qrc_load_build_export_reload` | QML-05 | Verified static source profile |
| QML-017-AC02 | `tests/test_qml_cpp_access.py::test_view_root_and_literal_object_name_property_access`; `tests/test_qml_cpp_access.py::test_qml_id_is_not_object_name_and_computed_lookup_not_guessed`; `tests/test_qt_access_providers.py::test_qqmlproperty_read_write_preserves_property_handle`; open completion: metadata-enriched object access | QML-05 | Partial; later gate open |
| QML-017-AC03 | `tests/test_qt_access_providers.py::test_qml_signals_to_cpp_private_slots_and_cpp_signals_to_qml_functions`; `tests/test_qt_access_providers.py::test_context_provider_is_limited_to_loaded_component`; `tests/test_qt_access_providers.py::test_context_object_and_conditional_or_dynamic_providers`; `tests/test_qt_access_providers.py::test_initial_property_provider_requires_declared_qml_property`; open completion: metadata-enriched provider scope | QML-05 | Partial; later gate open |
| QML-017-AC04 | `tests/test_qml_cpp_access.py::test_duplicate_object_names_do_not_select_first_child`; `tests/test_qt_access_providers.py::test_duplicate_context_provider_and_local_shadow_do_not_choose`; open completion: final incremental and consumer parity | QML-07 | Partial; later gate open |
