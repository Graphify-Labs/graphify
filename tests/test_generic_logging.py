from __future__ import annotations

import os
from pathlib import Path
import pytest

import graphify.extract as ex

def test_generic_logging_extraction(tmp_path, monkeypatch):
    # Change working directory to tmp_path so the extractor looks for logging_config.yaml there
    monkeypatch.chdir(tmp_path)
    
    # Write logging_config.yaml
    config_content = """
logging_rules:
  java:
    query: |
      (method_invocation
        object: (identifier) @log_obj (#match? @log_obj "{pattern}")
        name: (identifier) @log_level
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log|logger|timber)$"
  kotlin:
    query: |
      (call_expression
        (navigation_expression
          (identifier) @log_obj (#match? @log_obj "{pattern}")
          (identifier) @log_level
        )
        (value_arguments) @args
      )
    pattern: "(?i)^(log|logger|timber)$"
  c:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
  cpp:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
"""
    (tmp_path / "logging_config.yaml").write_text(config_content)
    
    # Create test source files
    java_file = tmp_path / "Test.java"
    java_file.write_text("""
class Test {
    void doSomething() {
        logger.info("Java log message");
    }
}
""")
    
    kotlin_file = tmp_path / "Test.kt"
    kotlin_file.write_text("""
fun doKotlin() {
    logger.warn("Kotlin log message")
}
""")
    
    c_file = tmp_path / "test.c"
    c_file.write_text("""
void doC() {
    log_info("C log message");
}
""")
    
    cpp_file = tmp_path / "test.cpp"
    cpp_file.write_text("""
void doCpp() {
    LOG_WARN("Cpp log message");
}
""")

    # First run without any flag/env-var. It should be disabled by default.
    from graphify.generic_logger import GenericLogExtractor
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor("logging_config.yaml"))
    
    files = [java_file, kotlin_file, c_file, cpp_file]
    result_disabled = ex.extract(files, cache_root=tmp_path / "cache_disabled", parallel=False)
    
    edges_disabled = result_disabled.get("edges", [])
    prints_log_edges_disabled = [e for e in edges_disabled if e.get("relation") == "PRINTS_LOG"]
    assert len(prints_log_edges_disabled) == 0, "Logging extraction should be disabled by default"
    
    # Now enable it via environment variable
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    # Reset internal loaded state to simulate fresh run
    ex.log_extractor._loaded = False
    
    result = ex.extract(files, cache_root=tmp_path / "cache_enabled", parallel=False)
    
    edges = result.get("edges", [])
    nodes = result.get("nodes", [])
    
    # Assert nodes exist
    log_nodes = [n for n in nodes if n.get("type") == "log"]
    assert len(log_nodes) >= 4
    
    # Assert edges exist
    prints_log_edges = [e for e in edges if e.get("relation") == "PRINTS_LOG"]
    assert len(prints_log_edges) == 4
    
    # Assert details of java log edge
    java_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "java")
    assert java_edge["source"].endswith("_dosomething")
    assert java_edge["target"] == 'logger.info("Java log message")'
    
    # Assert details of kotlin log edge
    kotlin_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "kotlin")
    assert kotlin_edge["source"].endswith("_dokotlin")
    assert kotlin_edge["target"] == 'logger.warn("Kotlin log message")'
    
    # Assert details of c log edge
    c_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "c")
    assert c_edge["source"].endswith("_doc")
    assert c_edge["target"] == 'log_info("C log message")'
    
    # Assert details of cpp log edge
    cpp_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "cpp")
    assert cpp_edge["source"].endswith("_docpp")
    assert cpp_edge["target"] == 'LOG_WARN("Cpp log message")'

def test_generic_logging_fallback_resolution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_content = """
logging_rules:
  c:
    query: |
      (call_expression
        function: (identifier) @log_obj (#match? @log_obj "{pattern}")
        arguments: (argument_list) @args
      )
    pattern: "(?i)^(log_.*)$"
"""
    (tmp_path / "logging_config.yaml").write_text(config_content)
    
    # C file with log inside non-standard / macro or top-level structure
    c_file = tmp_path / "toplevel.c"
    c_file.write_text("""
void top_log_test(void) {
    log_debug("Top level debug log");
}
""")
    
    monkeypatch.setenv("GRAPHIFY_EXTRACT_LOGS", "1")
    from graphify.generic_logger import GenericLogExtractor
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor("logging_config.yaml"))
    ex.log_extractor._loaded = False
    
    result = ex.extract([c_file], cache_root=tmp_path / "cache_fallback", parallel=False)
    edges = [e for e in result.get("edges", []) if e.get("relation") == "PRINTS_LOG"]
    assert len(edges) == 1
    assert edges[0]["source"].endswith("_top_log_test")
    assert edges[0]["target"] == 'log_debug("Top level debug log")'

