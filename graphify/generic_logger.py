import os
import yaml
from tree_sitter import Parser, Query, QueryCursor

class GenericLogExtractor:
    def __init__(self, config_path=None):
        self._config_path = config_path
        self.enabled = False
        self._loaded = False
        self.config = {}
        
        self.ext_map = {
            ".java": "java",
            ".kt": "kotlin",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".hpp": "cpp",
            ".h": "c"
        }

    def _ensure_loaded(self):
        if self._loaded:
            return
            
        cpath = self._config_path
        if cpath is None:
            cpath = os.environ.get("GRAPHIFY_LOGGING_CONFIG", "logging_config.yaml")
            
        is_enabled = os.environ.get("GRAPHIFY_EXTRACT_LOGS") == "1"
        self.enabled = is_enabled
        
        if not self.enabled:
            self._loaded = True
            return
            
        if not os.path.exists(cpath):
            print(f"[LogExtractor Warning] Configuration file {cpath} not found. Logging extraction disabled.", flush=True)
            self.enabled = False
            self._loaded = True
            return
            
        try:
            with open(cpath, "r") as f:
                self.config = yaml.safe_load(f).get("logging_rules", {})
        except Exception as e:
            print(f"[LogExtractor Warning] Failed to load configuration from {cpath}: {e}", flush=True)
            self.enabled = False
            
        self._loaded = True
        
    def inject_logs_to_graph(self, file_path, file_content, graph_builder):
        self._ensure_loaded()
        if not self.enabled:
            return
            
        _, ext = os.path.splitext(file_path)
        lang_key = self.ext_map.get(ext)
        if not lang_key or lang_key not in self.config:
            return  
            
        rule = self.config[lang_key]
        formatted_query = rule["query"].format(pattern=rule["pattern"])
        
        try:
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
                    while curr and curr.type not in ["function_declaration", "method_declaration", "function_definition"]:
                        curr = curr.parent
                    if curr:
                        def find_id(n):
                            if n.type == "identifier": return n
                            for c in n.children:
                                r = find_id(c)
                                if r: return r
                            return None
                        id_node = find_id(curr)
                        if id_node:
                            func_name_nodes = [id_node]
                
                if func_name_nodes and log_obj_nodes and args_nodes:
                    func_name = func_name_nodes[0].text.decode("utf-8", errors="ignore")
                    log_obj = log_obj_nodes[0].text.decode("utf-8", errors="ignore")
                    args = args_nodes[0].text.decode("utf-8", errors="ignore")
                    
                    source_id = None
                    # Search for callable node matching function name AND belonging to the same file
                    possible_nodes = [
                        n for n in graph_builder.result.get("nodes", []) 
                        if n.get("_callable") or n.get("type") in ("function", "method")
                    ]
                    for n in possible_nodes:
                        label = n.get("label", "")
                        n_file = n.get("source_file", "")
                        if n_file == file_path and (label == func_name or label == f".{func_name}()" or label == f"{func_name}()" or label.endswith(f"::{func_name}")):
                            source_id = n["id"]
                            break
                    if not source_id:
                        # Fallback 1: Any node in the same file matching the label
                        for n in graph_builder.result.get("nodes", []):
                            if n.get("source_file") == file_path and n.get("label") in (func_name, f".{func_name}()", f"{func_name}()"):
                                source_id = n["id"]
                                break
                    if not source_id:
                        # Fallback 2: File node for this file
                        file_nodes = [n for n in graph_builder.result.get("nodes", []) if n.get("source_file") == file_path and n.get("type") == "file"]
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
        except Exception as e:
            print(f"[LogExtractor Hook Warning] Skipping AST pass on {file_path}: {e}")
