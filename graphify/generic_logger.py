import hashlib
import json
import os
import sys
import threading
from tree_sitter import Parser, Query, QueryCursor

DEFAULT_LOGGING_RULES = {
    "java": {
        "query": """(method_invocation
  object: (identifier) @log_obj (#match? @log_obj "{pattern}")
  name: (identifier) @log_level
  arguments: (argument_list) @args
)""",
        "pattern": "(?i)^(log|logger|timber)$",
    },
    "kotlin": {
        "query": """(call_expression
  (navigation_expression
    (identifier) @log_obj (#match? @log_obj "{pattern}")
    (identifier) @log_level
  )
  (value_arguments) @args
)""",
        "pattern": "(?i)^(log|logger|timber)$",
    },
    "c": {
        "query": """(call_expression
  function: (identifier) @log_obj (#match? @log_obj "{pattern}")
  arguments: (argument_list) @args
)""",
        "pattern": "(?i)^(log_.*)$",
    },
    "cpp": {
        "query": """(call_expression
  function: (identifier) @log_obj (#match? @log_obj "{pattern}")
  arguments: (argument_list) @args
)""",
        "pattern": "(?i)^(log_.*)$",
    },
}

class GenericLogExtractor:
    def __init__(self, config_path=None):
        self._config_path = config_path
        self.enabled = False
        self._loaded = False
        self.config = {}
        self._lock = threading.Lock()
        
        self.ext_map = {
            ".java": "java",
            ".kt": "kotlin",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".hpp": "cpp",
            ".hxx": "cpp",
            ".hh": "cpp",
            ".h": "c",
        }

    def _ensure_loaded(self):
        cpath = self._config_path
        is_custom = cpath is not None or "GRAPHIFY_LOGGING_CONFIG" in os.environ
        if cpath is None:
            cpath = os.environ.get("GRAPHIFY_LOGGING_CONFIG", "logging_config.yaml")

        if self._loaded and getattr(self, "_current_config_path", None) == cpath:
            return

        with self._lock:
            if self._loaded and getattr(self, "_current_config_path", None) == cpath:
                return

            if not os.path.exists(cpath):
                if is_custom:
                    print(f"[LogExtractor Warning] Configuration file {cpath} not found. Logging extraction disabled.", file=sys.stderr, flush=True)
                    self.config = {}
                    self.enabled = False
                else:
                    # Default config not found in working directory - smoothly fall back to built-in rules
                    self.config = dict(DEFAULT_LOGGING_RULES)
                    self.enabled = True
                self._current_config_path = cpath
                self._loaded = True
                return

            new_config = {}
            new_enabled = False
            try:
                try:
                    import yaml
                except ImportError:
                    print("[LogExtractor Warning] PyYAML is not installed. Using built-in default logging rules.", file=sys.stderr, flush=True)
                    self.config = dict(DEFAULT_LOGGING_RULES)
                    self.enabled = True
                    self._current_config_path = cpath
                    self._loaded = True
                    return

                with open(cpath, "r", encoding="utf-8") as f:
                    loaded_data = yaml.safe_load(f)
                if loaded_data is None:
                    loaded_data = {}
                if not isinstance(loaded_data, dict):
                    print(f"[LogExtractor Warning] Configuration in {cpath} must be a YAML mapping/dictionary. Logging extraction disabled.", file=sys.stderr, flush=True)
                else:
                    rules = loaded_data.get("logging_rules", {})
                    if isinstance(rules, dict):
                        new_config = rules
                        new_enabled = True
                    else:
                        print(f"[LogExtractor Warning] 'logging_rules' in {cpath} must be a dictionary. Logging extraction disabled.", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"[LogExtractor Warning] Failed to load configuration from {cpath}: {e}", file=sys.stderr, flush=True)
                new_config = {}
                new_enabled = False

            self.config = new_config
            self.enabled = new_enabled
            self._current_config_path = cpath
            self._loaded = True

    def is_enabled(self):
        if os.environ.get("GRAPHIFY_EXTRACT_LOGS") != "1":
            return False
        self._ensure_loaded()
        return self.enabled

    def get_cache_kind(self) -> str:
        if not self.is_enabled():
            return "ast"
        try:
            cfg_bytes = json.dumps(self.config, sort_keys=True).encode("utf-8")
            fp = hashlib.sha256(cfg_bytes).hexdigest()[:8]
            return f"ast-logging-{fp}"
        except Exception:
            return "ast-logging"

    def _extract_func_name_node(self, curr):
        """Accurately extract the identifier/name node representing the enclosing function/method."""
        if not curr:
            return None

        # 1. Tree-sitter standard field 'name' (Java, Kotlin, etc.)
        name_node = curr.child_by_field_name("name")
        if name_node:
            return name_node

        # 2. C / C++ declarator traversal
        decl = curr.child_by_field_name("declarator")
        if decl:
            while decl and decl.type in (
                "function_declarator",
                "pointer_declarator",
                "reference_declarator",
                "parenthesized_declarator",
            ):
                inner = decl.child_by_field_name("declarator")
                if inner:
                    decl = inner
                else:
                    break
            if decl:
                inner_name = decl.child_by_field_name("name")
                if inner_name:
                    return inner_name
                return decl

        # 3. Parameter list predecessor fallback
        param_types = {
            "parameters",
            "parameter_list",
            "formal_parameters",
            "value_arguments",
            "value_parameters",
        }
        for idx, child in enumerate(curr.children):
            if child.type in param_types and idx > 0:
                prev = curr.children[idx - 1]
                if prev.type in ("identifier", "field_identifier"):
                    return prev
                inner = prev.child_by_field_name("declarator") or prev.child_by_field_name("name")
                if inner:
                    return inner

        return None

    def inject_logs_to_graph(self, file_path, file_content, graph_builder) -> bool:
        self._ensure_loaded()
        if not self.enabled:
            return True
            
        _, ext = os.path.splitext(file_path)
        lang_key = self.ext_map.get(ext.lower())
        if not lang_key or lang_key not in self.config:
            return True
            
        rule = self.config[lang_key]
        if not isinstance(rule, dict) or "query" not in rule:
            return True

        try:
            pattern = rule.get("pattern", "")
            formatted_query = rule["query"].replace("{pattern}", pattern)

            ts_language = graph_builder.get_tree_sitter_language(lang_key)
            query = Query(ts_language, formatted_query)
            
            parser = Parser(ts_language)
            tree = parser.parse(bytes(file_content, "utf8"))
            cursor = QueryCursor(query)
            matches = cursor.matches(tree.root_node)
            
            logs_by_source = {}
            for _, captures in matches:
                func_name_nodes = captures.get("func_name", [])
                log_obj_nodes = captures.get("log_obj", [])
                log_level_nodes = captures.get("log_level", [])
                args_nodes = captures.get("args", [])
                
                curr = None
                if not func_name_nodes and log_obj_nodes:
                    curr = log_obj_nodes[0]
                    while curr and curr.type not in [
                        "function_declaration",
                        "method_declaration",
                        "function_definition",
                        "constructor_declaration",
                        "constructor_definition",
                        "destructor_definition",
                        "destructor_declaration",
                        "lambda_expression",
                        "arrow_function",
                        "static_initializer",
                        "init_block",
                    ]:
                        curr = curr.parent

                    walker = curr
                    while walker and walker.type in (
                        "lambda_expression",
                        "arrow_function",
                        "static_initializer",
                        "init_block",
                    ):
                        p = walker.parent
                        while p and p.type not in [
                            "function_declaration",
                            "method_declaration",
                            "function_definition",
                            "constructor_declaration",
                            "constructor_definition",
                            "destructor_definition",
                            "destructor_declaration",
                        ]:
                            p = p.parent
                        if p:
                            walker = p
                            break
                        else:
                            break
                    if walker:
                        curr = walker

                    if curr:
                        id_node = self._extract_func_name_node(curr)
                        if id_node:
                            func_name_nodes = [id_node]
                
                if func_name_nodes and log_obj_nodes:
                    func_name = func_name_nodes[0].text.decode("utf-8", errors="ignore")
                    log_obj = log_obj_nodes[0].text.decode("utf-8", errors="ignore")
                    args = args_nodes[0].text.decode("utf-8", errors="ignore") if args_nodes else "()"
                    log_line = log_obj_nodes[0].start_point[0] + 1
                    
                    curr_start = curr.start_point[0] + 1 if curr else log_line
                    curr_end = curr.end_point[0] + 1 if curr else log_line
                    is_constructor = curr.type in ("constructor_declaration", "constructor_definition") if curr else False
                    is_destructor = curr.type in ("destructor_declaration", "destructor_definition") if curr else False

                    # Find enclosing class if any
                    enclosing_class = None
                    p = curr.parent if curr else None
                    while p:
                        if p.type in (
                            "class_declaration",
                            "class_definition",
                            "class_specifier",
                            "struct_specifier",
                            "interface_declaration",
                            "enum_declaration",
                        ):
                            cname_node = p.child_by_field_name("name")
                            if cname_node:
                                enclosing_class = cname_node.text.decode("utf-8", errors="ignore")
                                break
                        p = p.parent

                    source_id = None
                    best_cand = None
                    best_score = -1

                    for n in graph_builder.result.get("nodes", []):
                        if n.get("type") in ("log", "file"):
                            continue
                        n_file = n.get("source_file", "")
                        if n_file != file_path and not file_path.endswith(n_file):
                            continue
                        
                        loc = n.get("source_location", "")
                        n_line = None
                        if loc.startswith("L"):
                            num_part = loc[1:].split("-")[0]
                            if num_part.isdigit():
                                n_line = int(num_part)

                        label = n.get("label", "")
                        nid = n.get("id", "")
                        base_label = label.split("(")[0]
                        is_callable_class = bool(n.get("_callable_class"))

                        score = 0
                        in_range = (n_line is not None and curr_start <= n_line <= curr_end)
                        if in_range:
                            score += 50
                            if n_line == curr_start:
                                score += 20

                        name_match = (
                            base_label == func_name or
                            base_label == f".{func_name}" or
                            base_label.endswith(f".{func_name}") or
                            base_label.endswith(f"::{func_name}") or
                            nid.endswith(f"_{func_name.lower()}") or
                            nid.endswith(f"_{func_name.lower()}_{func_name.lower()}")
                        )

                        if is_destructor:
                            if f"~{func_name}" in label or f"~{func_name}" in nid:
                                score += 100
                        elif is_constructor:
                            if not is_callable_class and (name_match or label == f".{func_name}()"):
                                score += 100
                            elif is_callable_class and name_match:
                                score += 10
                        else:
                            if not is_callable_class and name_match:
                                score += 100
                            elif is_callable_class and name_match:
                                score += 10

                        if enclosing_class and enclosing_class.lower() in nid.lower():
                            score += 30

                        if score > best_score:
                            best_score = score
                            best_cand = n

                    if best_cand and best_score > 0:
                        source_id = best_cand["id"]

                    if not source_id:
                        # Fallback: File node for this file
                        file_nodes = [
                            n for n in graph_builder.result.get("nodes", [])
                            if (n.get("source_file") == file_path or file_path.endswith(n.get("source_file", "")))
                            and (n.get("label") == os.path.basename(file_path) or n.get("type") == "file")
                        ]
                        if file_nodes:
                            source_id = file_nodes[0]["id"]
                        else:
                            source_id = graph_builder.file_path
                    
                    if log_level_nodes:
                        log_level = log_level_nodes[0].text.decode("utf-8", errors="ignore")
                        log_prefix = f"{log_obj}.{log_level}"
                    else:
                        log_prefix = log_obj
                        
                    log_signature = f"{log_prefix}{args}"
                    if source_id not in logs_by_source:
                        logs_by_source[source_id] = []
                    logs_by_source[source_id].append((log_signature, log_line))

            for source_id, logs in logs_by_source.items():
                signatures = [sig for sig, _ in logs]
                unique_sigs = []
                for s in signatures:
                    if s not in unique_sigs:
                        unique_sigs.append(s)
                consolidated_target = " | ".join(unique_sigs)
                min_line = min(line for _, line in logs)
                lines_list = [line for _, line in logs]

                graph_builder.add_edge(
                    source=source_id,
                    target=consolidated_target,
                    relationship="PRINTS_LOG",
                    metadata={
                        "file": file_path,
                        "type": "EXTRACTED",
                        "lang": lang_key,
                        "lines": lines_list,
                    },
                    source_location=f"L{min_line}",
                )
            return True
        except Exception as e:
            print(f"[LogExtractor Hook Warning] Skipping AST pass on {file_path}: {e}", file=sys.stderr, flush=True)
            return False
