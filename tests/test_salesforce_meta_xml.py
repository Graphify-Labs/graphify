"""Tests for the Salesforce ``*-meta.xml`` extractor."""
from __future__ import annotations

from pathlib import Path

from graphify.detect import FileType, classify_file
from graphify.extract import _get_extractor, extract
from graphify.extractors.salesforce_meta_xml import (
    extract_salesforce_meta_xml,
    is_salesforce_meta_xml_path,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _labels(result: dict) -> set[str]:
    return {n["label"] for n in result["nodes"]}


def _refs(result: dict) -> set[str]:
    by_id = {n["id"]: n for n in result["nodes"]}
    return {by_id[e["target"]]["label"] for e in result["edges"]
            if e["relation"] == "references"}


PERMISSION_SET = """<?xml version="1.0" encoding="UTF-8"?>
<PermissionSet xmlns="http://soap.sforce.com/2006/04/metadata">
    <classAccesses>
        <apexClass>NotifyUser</apexClass>
        <enabled>true</enabled>
    </classAccesses>
    <fieldPermissions>
        <editable>true</editable>
        <field>Memory__c.Content__c</field>
        <readable>true</readable>
    </fieldPermissions>
</PermissionSet>
"""

CUSTOM_FIELD = """<?xml version="1.0" encoding="UTF-8"?>
<CustomField xmlns="http://soap.sforce.com/2006/04/metadata">
    <fullName>IsShared__c</fullName>
    <label>Is Shared</label>
    <type>Checkbox</type>
    <trackHistory>false</trackHistory>
</CustomField>
"""


def test_component_name_comes_from_the_filename(tmp_path: Path):
    f = _write(tmp_path / "MyOrgButlerUser.permissionset-meta.xml", PERMISSION_SET)
    assert "MyOrgButlerUser" in _labels(extract_salesforce_meta_xml(f))


def test_apex_class_grant_becomes_a_reference(tmp_path: Path):
    f = _write(tmp_path / "MyOrgButlerUser.permissionset-meta.xml", PERMISSION_SET)
    assert "NotifyUser" in _refs(extract_salesforce_meta_xml(f))


def test_qualified_field_references_both_object_and_field(tmp_path: Path):
    f = _write(tmp_path / "MyOrgButlerUser.permissionset-meta.xml", PERMISSION_SET)
    refs = _refs(extract_salesforce_meta_xml(f))
    assert {"Memory__c", "Content__c"} <= refs


def test_values_are_not_references(tmp_path: Path):
    """Negative control: enum and boolean element text must not become edges.

    `true`, `Checkbox` and `Is Shared` are values, not component names. Turning
    them into nodes would build god-nodes that every metadata file links to.
    """
    f = _write(tmp_path / "IsShared__c.field-meta.xml", CUSTOM_FIELD)
    result = extract_salesforce_meta_xml(f)
    assert _refs(result) == set()
    assert _labels(result) == {"IsShared__c.field-meta.xml", "IsShared__c"}


def test_display_text_is_not_a_reference(tmp_path: Path):
    """A `<label>` is free text, even when it reads exactly like an API name.

    Leaving a label at the API name is common, and it must not manufacture a
    dependency on the component that happens to share that name.
    """
    f = _write(tmp_path / "Status__c.field-meta.xml",
               '<?xml version="1.0"?><CustomField>'
               "<fullName>Status__c</fullName><label>Memory__c</label>"
               "<type>Picklist</type></CustomField>")
    assert "Memory__c" not in _refs(extract_salesforce_meta_xml(f))


def test_layout_pseudo_fields_are_not_references(tmp_path: Path):
    """Negative control: a layout's ALL-CAPS tokens are not components.

    `NAME` and `TASK.SUBJECT` are layout placeholders, not API names. They are
    also not unique, so binding them would wire unrelated layouts together.
    """
    f = _write(tmp_path / "Task-Task Layout.layout-meta.xml",
               '<?xml version="1.0"?><Layout><layoutSections><layoutColumns>'
               "<layoutItems><field>NAME</field></layoutItems>"
               "<layoutItems><field>TASK.SUBJECT</field></layoutItems>"
               "</layoutColumns></layoutSections></Layout>")
    refs = _refs(extract_salesforce_meta_xml(f))
    assert refs == set(), f"expected no references, got {refs}"


def test_custom_metadata_name_element_is_a_reference(tmp_path: Path):
    """`<name>` carries a real reference in custom-metadata records."""
    f = _write(tmp_path / "AccountHandler.md-meta.xml",
               '<?xml version="1.0"?><CustomMetadata>'
               "<values><field>Handler__c</field><value>CustomSetting__c</value></values>"
               "<name>CustomSetting__c</name></CustomMetadata>")
    assert "CustomSetting__c" in _refs(extract_salesforce_meta_xml(f))


def test_referenced_components_are_sourceless(tmp_path: Path):
    f = _write(tmp_path / "MyOrgButlerUser.permissionset-meta.xml", PERMISSION_SET)
    result = extract_salesforce_meta_xml(f)
    by_label = {n["label"]: n for n in result["nodes"]}
    assert by_label["NotifyUser"]["source_file"] == ""
    assert by_label["MyOrgButlerUser"]["source_file"].endswith("-meta.xml")


def test_field_is_contained_by_its_object(tmp_path: Path):
    obj = _write(tmp_path / "objects/Memory__c/Memory__c.object-meta.xml",
                 '<?xml version="1.0"?><CustomObject/>')
    field = _write(tmp_path / "objects/Memory__c/fields/IsShared__c.field-meta.xml",
                   CUSTOM_FIELD)
    result = extract_salesforce_meta_xml(field)
    by_id = {n["id"]: n for n in result["nodes"]}
    owners = {by_id[e["source"]]["label"] for e in result["edges"]
              if e["relation"] == "contains"
              and by_id[e["target"]]["label"] == "IsShared__c"}
    assert "Memory__c" in owners
    assert obj.exists()


def test_apex_sidecar_is_left_to_the_apex_extractor(tmp_path: Path):
    f = _write(tmp_path / "AgentMemory.cls-meta.xml",
               '<?xml version="1.0"?><ApexClass><apiVersion>64.0</apiVersion></ApexClass>')
    assert not is_salesforce_meta_xml_path(f)
    assert extract_salesforce_meta_xml(f) == {"nodes": [], "edges": []}


def test_plain_xml_is_not_claimed(tmp_path: Path):
    """Negative control: only `*-meta.xml` is claimed.

    Claiming `.xml` outright would sweep every pom.xml and web.xml in every
    repository into the graph, which is a separate decision from Salesforce.
    """
    other = _write(tmp_path / "web.xml", "<web-app/>")
    assert not is_salesforce_meta_xml_path(other)
    assert classify_file(other) is None


def test_metadata_takes_the_ast_path(tmp_path: Path):
    f = _write(tmp_path / "Memory__c.object-meta.xml", '<?xml version="1.0"?><CustomObject/>')
    assert classify_file(f) is FileType.CODE
    assert _get_extractor(f) is extract_salesforce_meta_xml


def test_doctype_is_refused(tmp_path: Path):
    f = _write(tmp_path / "Evil.object-meta.xml",
               '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><CustomObject/>')
    result = extract_salesforce_meta_xml(f)
    assert result["nodes"] == [] and "DOCTYPE" in result["error"]


def test_malformed_xml_reports_an_error(tmp_path: Path):
    f = _write(tmp_path / "Broken.object-meta.xml", "<CustomObject><unclosed>")
    result = extract_salesforce_meta_xml(f)
    assert result["nodes"] == [] and "parse error" in result["error"]


def test_permission_set_reaches_the_real_apex_class(tmp_path: Path):
    """The grant must land on the class definition, not a name-only leaf."""
    apex = _write(tmp_path / "classes/NotifyUser.cls",
                  "public with sharing class NotifyUser {}\n")
    perm = _write(tmp_path / "permissionsets/MyOrgButlerUser.permissionset-meta.xml",
                  PERMISSION_SET)
    result = extract([apex, perm], cache_root=tmp_path)

    by_id = {n["id"]: n for n in result["nodes"]}
    hits = [e for e in result["edges"]
            if e["relation"] == "references"
            and by_id.get(e["target"], {}).get("label") == "NotifyUser"]
    assert hits, "no reference edge to NotifyUser"
    assert Path(by_id[hits[0]["target"]]["source_file"]).name == "NotifyUser.cls"


def test_metadata_is_collected_when_following_symlinks(tmp_path: Path):
    """Regression: collect_files has two walks, and only one had the exception.

    The symlink-following walk gated on extension alone, so with
    follow_symlinks=True every `*-meta.xml` was silently dropped.
    """
    from graphify.extract import collect_files

    _write(tmp_path / "objects/Memory__c/Memory__c.object-meta.xml",
           '<?xml version="1.0"?><CustomObject/>')
    for follow in (False, True):
        found = {p.name for p in collect_files(tmp_path, follow_symlinks=follow)}
        assert "Memory__c.object-meta.xml" in found, f"dropped with follow={follow}"


def test_utf16_doctype_is_refused(tmp_path: Path):
    """The DOCTYPE screen matches ASCII bytes, so UTF-16 would walk past it.

    ElementTree honours the encoding declaration and would expand the entity,
    which is the billion-laughs hole the screen exists to close.
    """
    f = tmp_path / "Evil.object-meta.xml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(
        '<?xml version="1.0" encoding="UTF-16"?>'
        '<!DOCTYPE x [<!ENTITY a "boom">]><CustomObject/>'.encode("utf-16"))
    result = extract_salesforce_meta_xml(f)
    assert result["nodes"] == [] and "UTF-8" in result["error"]


def test_ordinary_utf8_metadata_is_still_accepted(tmp_path: Path):
    """Guard the other direction: the encoding check must not reject real files."""
    f = _write(tmp_path / "Memory__c.object-meta.xml",
               '<?xml version="1.0" encoding="UTF-8"?><CustomObject/>')
    assert "Memory__c" in _labels(extract_salesforce_meta_xml(f))
