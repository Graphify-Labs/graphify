from pathlib import Path
from graphify.extract import extract_php
import pytest

def test_php_closures(tmp_path):
    src = b'''<?php
$app->get('/api', function() {
    return 1;
});
$fn = fn($x) => $x + 1;
'''
    php_file = tmp_path / 'dummy.php'
    php_file.write_bytes(src)
    
    res = extract_php(php_file)
    if res.get('error'):
        pytest.skip(res['error'])
        
    nodes = {n['id']: n for n in res['nodes']}
    labels = {n['label']: n for n in res['nodes']}
    
    # Assert closures are correctly generated
    assert '{closure@2}()' in labels, "Missing anonymous_function_creation_expression node"
    assert '{closure@5}()' in labels, "Missing arrow_function node"
    
    closure_1 = labels['{closure@2}()']
    closure_2 = labels['{closure@5}()']
    
    # Check edges
    edges = res['edges']
    assert any(e['source'] == 'dummy.php' and e['target'] == closure_1['id'] and e['relation'] == 'contains' for e in edges), "Missing contains edge for closure_1"
    assert any(e['source'] == 'dummy.php' and e['target'] == closure_2['id'] and e['relation'] == 'contains' for e in edges), "Missing contains edge for closure_2"

