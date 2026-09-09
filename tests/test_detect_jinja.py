from graphify.detect import DOC_EXTENSIONS

def test_jinja2_extensions_are_documents():
    assert '.j2' in DOC_EXTENSIONS
    assert '.jinja' in DOC_EXTENSIONS
    assert '.jinja2' in DOC_EXTENSIONS
