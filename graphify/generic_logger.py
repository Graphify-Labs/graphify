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
                    possible_nodes = [n for n in graph_builder.result.get("nodes", []) if n.get("_callable")]
                    for n in possible_nodes:
                        label = n.get("label", "")
                        if label == func_name or label == f".{func_name}()" or label == f"{func_name}()":
                            source_id = n["id"]
                            break
                    if not source_id:
                        nodes = graph_builder.result.get("nodes", [])
                        source_id = nodes[0]["id"] if nodes else f"{file_path}::{func_name}"
                    
                    if log_level_nodes:
                        log_level = log_level_nodes[0].text.decode("utf-8", errors="ignore")
                        log_prefix = f"{log_obj}.{log_level}"
                    else:
                        log_prefix = log_obj
                        
                    log_signature = f"{log_prefix}{args}"
                    
                    graph_builder.add_edge(
                        source=source_id,
                        target=log_signature,
                        relationship="PRINTS_LOG",
                        metadata={"file": file_path, "type": "EXTRACTED", "lang": lang_key}
                    )
        except Exception as e:
            print(f"[LogExtractor Hook Warning] Skipping AST pass on {file_path}: {e}")
