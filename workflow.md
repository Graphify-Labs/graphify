1. Executive Summary & Core Rationale
The Problem
Traditional code indexers track where classes and modules live, but they miss runtime context—specifically logging behaviors. In complex, multi-language systems (e.g., Android Framework code running an intersection of Java, Kotlin, C, and C++), debug loops require knowing exactly which function emits which error strings or logs. Relying on an AI agent to continuously grep or re-scan entire files for log invocations wastes context windows, driving up latency and token costs.

The Solution: Abstract Syntax Tree (AST) Edge Injection
Graphify builds local structural graphs deterministically using Tree-sitter. By intercepting Graphify’s local ingestion loop, we can programmatically scan for log expressions alongside standard call trees. Moving the query patterns to a single logging_config.yaml file decouples development from individual languages, enabling unified multi-language tracking without code rewrite overhead.

The Complete Agentic Workflow Prompt (With Git Branch Automation)
As an expert senior software engineer and git automation agent, follow this complete, step-by-step workflow to create, implement, modify, and cleanly branch a config-driven logging extraction fork of Graphify.

### Step 1: Initialize the Working Space & Branching Strategy
1. Clone the Graphify core codebase from 'https://github.com/Graphify-Labs/graphify' into a folder named 'graphify-logging-fork'.
2. Navigate into the folder: `cd graphify-logging-fork`
3. Create and immediately switch to a dedicated feature branch for this modification:
   git checkout -b feature/generic-ast-logging-extractor

### Step 2: Set Up Environment & Dependencies
1. Initialize an isolated virtual environment using `uv venv` or standard `python -m venv .venv`.
2. Activate the environment and install Graphify core dependencies along with the Tree-sitter language libraries required for a multi-language framework scan:
   pip install tree-sitter-java tree-sitter-kotlin tree-sitter-c tree-sitter-cpp pyyaml

### Step 3: Implement the Configuration-Driven Extraction Hook
Create a brand new file named `graphify/generic_logger.py` containing the following decoupled execution engine:

```python
import os
import yaml
from tree_sitter import Language, Parser

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
            query = ts_language.query(formatted_query)
            
            parser = Parser(ts_language)
            tree = parser.parse(bytes(file_content, "utf8"))
            captures = query.captures(tree.root_node)
            
            current_function = None
            log_data = {}
            
            for node, tag in captures:
                text = node.text.decode('utf-8', errors='ignore')
                
                if tag == "func_name":
                    current_function = f"{file_path}::{text}"
                    log_data = {}
                elif tag == "log_obj":
                    log_data["obj"] = text
                elif tag == "log_level":
                    log_data["level"] = text
                elif tag == "args":
                    log_data["args"] = text
                    
                    if current_function:
                        log_prefix = f"{log_data.get('obj', 'log')}.{log_data.get('level', '')}" if "level" in log_data else log_data.get('obj', 'log')
                        log_signature = f"{log_prefix}{log_data.get('args', '()')}"
                        
                        graph_builder.add_edge(
                            source=current_function,
                            target=log_signature,
                            relationship="PRINTS_LOG",
                            metadata={"file": file_path, "type": "EXTRACTED", "lang": lang_key}
                        )
        except Exception as e:
            print(f"[LogExtractor Hook Warning] Skipping AST pass on {file_path}: {e}")


Step 4: Intercept Graphify Ingestion Loop
Open graphify/extract.py.

Import GenericLogExtractor at the top of the file:
from graphify.generic_logger import GenericLogExtractor

Instantiate log_extractor = GenericLogExtractor() right alongside its native parser setups.

Locate the core file processing block (e.g., process_single_file). Append the following custom hook execution pass straight at the tail end of the function logic:
log_extractor.inject_logs_to_graph(file_path, content, graph_builder)

Step 5: Validate build and Check-In Code to Branch
Compile and link the package updates to verify there are no hidden syntax formatting or execution bugs:
pip install -e .

Run git status to verify modified and untracked files are exactly what we expect.

Stage all new additions and source modifications:
git add .

Formally commit the workflow changes with a clear, descriptive atomic message:
git commit -m "feat: implement generic config-driven logging extraction rules for mixed-mode codebases"

## Verification Strategy

Once your agent finishes running this prompt loop, you can verify that the branch lifecycle completed correctly by checking your local git status. Run this from your terminal inside the root of your newly minted fork repository:

```bash
# Verify you are safely nested on your custom feature branch
git branch

# Verify your modifications are completely captured and committed cleanly
git log -n 1