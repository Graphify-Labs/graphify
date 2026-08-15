from pathlib import Path

from graphify.detect import FileType, classify_file
from graphify.extract import (
    _get_extractor,
    collect_files,
    extract_groovy,
    extract_jenkinsfile,
)


JENKINSFILE = """\
@Library('platform-shared') _
def deployApp(String environment) {
  sh "deploy ${environment}"
  notifyTeam()
}
def notifyTeam() {
  echo 'deployed'
}
pipeline {
  agent { docker { image 'python:3.12' } }
  stages {
    stage('Build') {
      steps {
        sh 'make build'
        checkout scm
        docker.build('example/app:${BUILD_NUMBER}')
      }
    }
    stage('Test') {
      steps {
        sh(script: 'pytest')
        deployApp('prod')
      }
    }
    stage('Fanout') {
      parallel {
        stage('Linux') {
          steps { sh 'make linux' }
        }
        stage('Windows') {
          steps { sh 'make windows' }
        }
      }
    }
  }
}
"""


def test_jenkinsfile_extracts_pipeline_stages_steps_and_images(tmp_path: Path):
    path = tmp_path / "Jenkinsfile"
    path.write_text(JENKINSFILE)

    result = extract_jenkinsfile(path)

    assert "error" not in result
    by_label = {}
    for node in result["nodes"]:
        by_label.setdefault(node["label"], []).append(node)

    assert by_label["JenkinsPipeline"][0]["type"] == "jenkins_pipeline"
    assert "Build" in by_label
    assert "Test" in by_label
    assert "sh" in by_label
    assert "checkout" in by_label
    assert "docker.build" in by_label
    assert "python:3.12" in by_label
    assert "example/app:${BUILD_NUMBER}" in by_label
    assert "platform-shared" in by_label
    assert by_label["deployApp"][0]["type"] == "groovy_function"
    assert by_label["notifyTeam"][0]["type"] == "groovy_function"
    assert "JenkinsParallel" in by_label
    assert "Linux" in by_label
    assert "Windows" in by_label

    relations = {(edge["relation"], edge["source"], edge["target"]) for edge in result["edges"]}
    pipeline_id = by_label["JenkinsPipeline"][0]["id"]
    build_id = by_label["Build"][0]["id"]
    image_id = by_label["python:3.12"][0]["id"]
    assert ("contains", pipeline_id, build_id) in relations
    assert ("uses_image", pipeline_id, image_id) in relations
    library_id = by_label["platform-shared"][0]["id"]
    assert ("uses_library", pipeline_id, library_id) in relations
    deploy_id = by_label["deployApp"][0]["id"]
    notify_id = by_label["notifyTeam"][0]["id"]
    parallel_id = by_label["JenkinsParallel"][0]["id"]
    linux_id = by_label["Linux"][0]["id"]
    windows_id = by_label["Windows"][0]["id"]
    assert any(
        relation == "calls" and target == deploy_id
        for relation, _source, target in relations
    )
    assert ("calls", deploy_id, notify_id) in relations
    assert ("contains", by_label["Fanout"][0]["id"], parallel_id) in relations
    assert ("contains", parallel_id, linux_id) in relations
    assert ("contains", parallel_id, windows_id) in relations


def test_jenkinsfile_is_code_and_uses_special_extractor(tmp_path: Path):
    path = tmp_path / "Jenkinsfile"
    path.write_text("node { stage('Build') { sh 'make' } }\n")

    assert classify_file(path) is FileType.CODE
    assert _get_extractor(path) is extract_jenkinsfile


def test_collect_files_includes_extensionless_jenkinsfile(tmp_path: Path):
    jenkinsfile = tmp_path / "Jenkinsfile"
    groovy = tmp_path / "build.groovy"
    jenkinsfile.write_text("pipeline { agent any }\n")
    groovy.write_text("class Build {}\n")

    assert collect_files(tmp_path) == sorted([jenkinsfile, groovy])


def test_groovy_files_keep_the_generic_groovy_extractor(tmp_path: Path):
    path = tmp_path / "build.groovy"
    path.write_text("class Build {}\n")

    assert _get_extractor(path) is extract_groovy
