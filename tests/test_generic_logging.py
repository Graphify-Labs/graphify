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
      (method_declaration
        name: (identifier) @func_name
        body: (block
          (expression_statement
            (method_invocation
              object: (identifier) @log_obj (#match? @log_obj "{pattern}")
              name: (identifier) @log_level
              arguments: (argument_list) @args
            )
          )
        )
      )
    pattern: "^(log|logger)$"
  kotlin:
    query: |
      (function_declaration
        (identifier) @func_name
        (function_body
          (block
            (call_expression
              (navigation_expression
                (identifier) @log_obj (#match? @log_obj "{pattern}")
                (identifier) @log_level
              )
              (value_arguments) @args
            )
          )
        )
      )
    pattern: "^(log|logger)$"
  c:
    query: |
      (function_definition
        declarator: (function_declarator
          declarator: (identifier) @func_name
        )
        body: (compound_statement
          (expression_statement
            (call_expression
              function: (identifier) @log_obj (#match? @log_obj "{pattern}")
              arguments: (argument_list) @args
            )
          )
        )
      )
    pattern: "^(log_.*|LOG_.*)$"
  cpp:
    query: |
      (function_definition
        declarator: (function_declarator
          declarator: (identifier) @func_name
        )
        body: (compound_statement
          (expression_statement
            (call_expression
              function: (identifier) @log_obj (#match? @log_obj "{pattern}")
              arguments: (argument_list) @args
            )
          )
        )
      )
    pattern: "^(log_.*|LOG_.*)$"
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

    # We need to re-instantiate GenericLogExtractor inside extract.py to read the new config in tmp_path
    # Since log_extractor is a module-level variable, we can reload it or re-instantiate it
    from graphify.generic_logger import GenericLogExtractor
    monkeypatch.setattr(ex, "log_extractor", GenericLogExtractor("logging_config.yaml"))

    # Run extraction (non-parallel to avoid pickle/subprocess cwd mismatch issues in tests)
    files = [java_file, kotlin_file, c_file, cpp_file]
    result = ex.extract(files, cache_root=tmp_path / "cache", parallel=False)
    
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
    assert java_edge["source"].endswith("::doSomething")
    assert java_edge["target"] == 'logger.info("Java log message")'
    
    # Assert details of kotlin log edge
    kotlin_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "kotlin")
    assert kotlin_edge["source"].endswith("::doKotlin")
    assert kotlin_edge["target"] == 'logger.warn("Kotlin log message")'
    
    # Assert details of c log edge
    c_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "c")
    assert c_edge["source"].endswith("::doC")
    assert c_edge["target"] == 'log_info("C log message")'
    
    # Assert details of cpp log edge
    cpp_edge = next(e for e in prints_log_edges if e.get("metadata", {}).get("lang") == "cpp")
    assert cpp_edge["source"].endswith("::doCpp")
    assert cpp_edge["target"] == 'LOG_WARN("Cpp log message")'
