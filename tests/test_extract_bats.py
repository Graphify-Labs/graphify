from pathlib import Path
import pytest
from graphify.extractors.bash import extract_bash


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

#@test
function preceding_comment_form() {
  run bar
}
'''
    bats_file = tmp_path / 'dummy.bats'
    bats_file.write_bytes(src)

    res = extract_bash(bats_file)
    if res.get('error'):
        pytest.skip(res['error'])

    nodes_by_label = {n['label']: n for n in res['nodes']}

    assert 'addition using bc' in nodes_by_label, "Missing native test node"
    assert nodes_by_label['addition using bc']['metadata']['kind'] == 'bash_test'

    assert 'invoking_foo_without_arguments_prints_usage()' in nodes_by_label, "Missing comment-form test node"
    assert nodes_by_label['invoking_foo_without_arguments_prints_usage()']['metadata']['kind'] == 'bash_test'

    assert 'preceding_comment_form()' in nodes_by_label, "Missing preceding comment-form test node"
    assert nodes_by_label['preceding_comment_form()']['metadata']['kind'] == 'bash_test'


def test_bats_native_call_edges_attribute_to_test(tmp_path):
    src = b'''
helper_fn() {
  echo "helper"
}

@test "native form calls helper" {
  helper_fn
}
'''
    bats_file = tmp_path / 'test_calls.bats'
    bats_file.write_bytes(src)

    res = extract_bash(bats_file)
    if res.get('error'):
        pytest.skip(res['error'])

    # Find test node, entrypoint node, and helper function node
    test_node = next(n for n in res['nodes'] if n['label'] == 'native form calls helper')
    entry_node = next(n for n in res['nodes'] if n['id'].endswith('__entry'))
    helper_node = next(n for n in res['nodes'] if n['label'] == 'helper_fn()')

    call_edges = [
        (e['source'], e['target'])
        for e in res['edges']
        if e['relation'] == 'calls'
    ]

    # Test node should call helper_fn
    assert (test_node['id'], helper_node['id']) in call_edges, (
        "Call inside native Bats test body must attribute to the test node"
    )
    # Entrypoint should NOT call helper_fn
    assert (entry_node['id'], helper_node['id']) not in call_edges, (
        "Call inside native Bats test body must not leak into script entrypoint"
    )


def test_bats_comment_scoping_negative(tmp_path):
    src = b'''
echo_fn() {
  echo "#@test in string"
}

heredoc_fn() {
  cat <<'EOF'
#@test inside heredoc
EOF
}

unrelated_comment_fn() {
  local x=1
  # Some discussion mentioning #@test later in body
  echo "$x"
}
'''
    sh_file = tmp_path / 'regular.sh'
    sh_file.write_bytes(src)

    res = extract_bash(sh_file)
    if res.get('error'):
        pytest.skip(res['error'])

    nodes_by_label = {n['label']: n for n in res['nodes']}

    assert nodes_by_label['echo_fn()']['metadata']['kind'] == 'bash_function'
    assert nodes_by_label['heredoc_fn()']['metadata']['kind'] == 'bash_function'
    assert nodes_by_label['unrelated_comment_fn()']['metadata']['kind'] == 'bash_function'
