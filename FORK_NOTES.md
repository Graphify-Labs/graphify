# Fork Notes

Forked from: https://github.com/safishamsi/graphify  
Fork remote: https://github.com/justinhchae/graphify.git  
Branch: feat/esri-ps-extensions  

## Esri PS Patches

**2026-06-25**

- `graphify/__main__.py`: Restored `_load_dotenv()` call before `from graphify.paths import GRAPHIFY_OUT`. Loads `.env` from CWD at startup so `GRAPHIFY_OUT` and API keys are available at import time. Falls back to manual parse if `python-dotenv` is not installed.
- `graphify/detect.py`: Added `.pyt` to `CODE_EXTENSIONS`. ArcGIS Pro Python Toolbox files are treated as code (LLM semantic extraction).
- `graphify/detect.py`: Added `.bat` to `CODE_EXTENSIONS`. Windows workflow launcher scripts are treated as code (LLM semantic extraction).

## Rebase Workflow

```
git fetch upstream
git rebase upstream/main
```

Re-run `pip install -e .` and rebuild graphs after each rebase.
