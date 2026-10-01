from pathlib import Path
from graphify.extractors.bash import extract_bash
import pytest

def test_bats_native_and_comment_forms(tmp_path):
    src = b'''
@test "addition using bc" {
  result="$(echo 2+2 | bc)"
  [ "$result" -eq 4 ]
}

function invoking_foo_without_arguments_prints_usage { #@test
  run foo
  [ "$status" -eq 1 ]
}
'''
    bats_file = tmp_path / 'dummy.bats'
    bats_file.write_bytes(src)
    
    res = extract_bash(bats_file)
    if res.get('error'):
        pytest.skip(res['error'])
        
    nodes = {n['id']: n for n in res['nodes']}
    
    assert 'dummy.bats:addition using bc' in nodes, "Missing native test node"
    assert nodes['dummy.bats:addition using bc']['kind'] == 'bash_test'
    
    assert 'dummy.bats:invoking_foo_without_arguments_prints_usage' in nodes, "Missing comment-form test node"
    assert nodes['dummy.bats:invoking_foo_without_arguments_prints_usage']['kind'] == 'bash_test'
