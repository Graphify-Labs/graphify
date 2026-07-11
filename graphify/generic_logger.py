import os
import yaml
from tree_sitter import Parser, Query, QueryCursor

class GenericLogExtractor:
    def __init__(self, config_path="logging_config.yaml"):
        self.enabled = os.path.exists(config_path)
        if not self.enabled:
            return
            
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f).get("logging_rules", {})
            
        self.ext_map = {
            ".java": "java",
            ".kt": "kotlin",
            ".c": "c",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".hpp": "cpp",
            ".h": "c"
        }
        
    def inject_logs_to_graph(self, file_path, file_content, graph_builder):
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
                
                if func_name_nodes and log_obj_nodes and args_nodes:
                    func_name = func_name_nodes[0].text.decode("utf-8", errors="ignore")
                    log_obj = log_obj_nodes[0].text.decode("utf-8", errors="ignore")
                    args = args_nodes[0].text.decode("utf-8", errors="ignore")
                    
                    current_function = f"{file_path}::{func_name}"
                    
                    if log_level_nodes:
                        log_level = log_level_nodes[0].text.decode("utf-8", errors="ignore")
                        log_prefix = f"{log_obj}.{log_level}"
                    else:
                        log_prefix = log_obj
                        
                    log_signature = f"{log_prefix}{args}"
                    
                    graph_builder.add_edge(
                        source=current_function,
                        target=log_signature,
                        relationship="PRINTS_LOG",
                        metadata={"file": file_path, "type": "EXTRACTED", "lang": lang_key}
                    )
        except Exception as e:
            print(f"[LogExtractor Hook Warning] Skipping AST pass on {file_path}: {e}")
