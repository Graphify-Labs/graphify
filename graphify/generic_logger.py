import hashlib
import json
import os
import sys
import threading
import yaml
from tree_sitter import Parser, Query, QueryCursor

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
        if cpath is None:
            cpath = os.environ.get("GRAPHIFY_LOGGING_CONFIG", "logging_config.yaml")

        if self._loaded and getattr(self, "_current_config_path", None) == cpath:
            return

        with self._lock:
            if self._loaded and getattr(self, "_current_config_path", None) == cpath:
                return

            if not os.path.exists(cpath):
                print(f"[LogExtractor Warning] Configuration file {cpath} not found. Logging extraction disabled.", flush=True)
                self.config = {}
                self.enabled = False
                self._current_config_path = cpath
                self._loaded = True
                return

            new_config = {}
            new_enabled = False
            try:
                with open(cpath, "r", encoding="utf-8") as f:
                    loaded_data = yaml.safe_load(f)
                if loaded_data is None:
                    loaded_data = {}
                if not isinstance(loaded_data, dict):
                    print(f"[LogExtractor Warning] Configuration in {cpath} must be a YAML mapping/dictionary. Logging extraction disabled.", flush=True)
                else:
                    rules = loaded_data.get("logging_rules", {})
                    if isinstance(rules, dict):
                        new_config = rules
                        new_enabled = True
                    else:
                        print(f"[LogExtractor Warning] 'logging_rules' in {cpath} must be a dictionary. Logging extraction disabled.", flush=True)
            except Exception as e:
                print(f"[LogExtractor Warning] Failed to load configuration from {cpath}: {e}", flush=True)
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
                
                if not func_name_nodes and log_obj_nodes:
                    curr = log_obj_nodes[0]
                    while curr and curr.type not in [
                        "function_declaration",
                        "method_declaration",
                        "function_definition",
                        "constructor_declaration",
                        "constructor_definition",
                        "destructor_definition",
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
                    
                    source_id = None
                    # Search for callable node matching function name AND belonging to the same file
                    possible_nodes = [
                        n for n in graph_builder.result.get("nodes", []) 
                        if n.get("_callable") or n.get("type") in ("function", "method")
                    ]
                    for n in possible_nodes:
                        label = n.get("label", "")
                        n_file = n.get("source_file", "")
                        base_label = label.split("(")[0]
                        if n_file == file_path and (base_label == func_name or base_label.endswith(f".{func_name}") or base_label.endswith(f"::{func_name}") or base_label == f"~{func_name}"):
                            source_id = n["id"]
                            break
                    if not source_id:
                        # Fallback 1: Any node in the same file matching the label
                        for n in graph_builder.result.get("nodes", []):
                            label = n.get("label", "")
                            base_label = label.split("(")[0]
                            if n.get("source_file") == file_path and (base_label == func_name or base_label.endswith(f".{func_name}") or base_label.endswith(f"::{func_name}") or base_label == f"~{func_name}"):
                                source_id = n["id"]
                                break
                    if not source_id:
                        # Fallback 2: File node for this file
                        file_nodes = [
                            n for n in graph_builder.result.get("nodes", [])
                            if n.get("source_file") == file_path and (n.get("label") == os.path.basename(file_path) or n.get("type") == "file")
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
                    if log_signature not in logs_by_source[source_id]:
                        logs_by_source[source_id].append(log_signature)

            for source_id, logs in logs_by_source.items():
                consolidated_target = " | ".join(logs)
                graph_builder.add_edge(
                    source=source_id,
                    target=consolidated_target,
                    relationship="PRINTS_LOG",
                    metadata={"file": file_path, "type": "EXTRACTED", "lang": lang_key}
                )
            return True
        except Exception as e:
            print(f"[LogExtractor Hook Warning] Skipping AST pass on {file_path}: {e}", file=sys.stderr, flush=True)
            return False
