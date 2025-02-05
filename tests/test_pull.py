import argparse
from pathlib import Path

import pytest

from opensafely import pull

project_fixture_path = Path(__file__).parent / "fixtures" / "projects"


def tag(image):
    return f"{pull.REGISTRY}/{image}:latest"


def test_default_no_local_images(run, capsys):

    run.expect(["docker", "info"])
    run.expect(["docker", "images", "ghcr.io/opensafely-core/*", "--no-trunc", "--format={{.Repository}}={{.ID}}"], stdout="")

    pull.main(image="all", force=False)
    out, err = capsys.readouterr()
    assert err == ""
    assert out.strip() == "No OpenSAFELY docker images found to update."


def test_default_no_local_images_force(run, capsys):

    run.expect(["docker", "info"])
    run.expect(["docker", "images", "ghcr.io/opensafely-core/*", "--no-trunc", "--format={{.Repository}}={{.ID}}"], stdout="")
    run.expect(["docker", "pull", tag("cohortextractor")])
    run.expect(["docker", "pull", tag("cohortextractor-v2")])
    run.expect(["docker", "pull", tag("jupyter")])
    run.expect(["docker", "pull", tag("python")])
    run.expect(["docker", "pull", tag("r")])
    run.expect(["docker", "pull", tag("stata-mp")])
    run.expect(["docker", "image", "prune", "--force"])

    pull.main(image="all", force=True)
    out, err = capsys.readouterr()
    assert err == ""
    assert out.splitlines() == [
        "Updating OpenSAFELY cohortextractor image",
        "Updating OpenSAFELY cohortextractor-v2 image",
        "Updating OpenSAFELY jupyter image",
        "Updating OpenSAFELY python image",
        "Updating OpenSAFELY r image",
        "Updating OpenSAFELY stata-mp image",
        "Cleaning up old images",
    ]


def test_default_with_local_images(run, capsys):

    run.expect(["docker", "info"])
    run.expect(
        ["docker", "images", "ghcr.io/opensafely-core/*", "--no-trunc", "--format={{.Repository}}={{.ID}}"],
        stdout="ghcr.io/opensafely-core/r=sha",
    )
    run.expect(["docker", "pull", tag("r")])
    run.expect(["docker", "image", "prune", "--force"])

    pull.main(image="all", force=False)
    out, err = capsys.readouterr()
    assert err == ""
    assert out.splitlines() == [
        "Updating OpenSAFELY r image",
        "Cleaning up old images",
    ]


def test_specific_image(run, capsys):

    run.expect(["docker", "info"])
    run.expect(["docker", "images", "ghcr.io/opensafely-core/*", "--no-trunc", "--format={{.Repository}}={{.ID}}"], stdout="")
    run.expect(["docker", "pull", tag("r")])
    run.expect(["docker", "image", "prune", "--force"])

    pull.main(image="r", force=False)
    out, err = capsys.readouterr()
    assert err == ""
    assert out.splitlines() == [
        "Updating OpenSAFELY r image",
        "Cleaning up old images",
    ]


def test_project(run, capsys):

    run.expect(["docker", "info"])
    run.expect(["docker", "images", "ghcr.io/opensafely-core/*", "--no-trunc", "--format={{.Repository}}={{.ID}}"], stdout="")
    run.expect(["docker", "pull", tag("cohortextractor")])
    run.expect(["docker", "pull", tag("python")])
    run.expect(["docker", "pull", tag("jupyter")])
    run.expect(["docker", "image", "prune", "--force"])

    pull.main(project=project_fixture_path / "project.yaml")
    out, err = capsys.readouterr()
    assert err == ""
    assert out.splitlines() == [
        "Updating OpenSAFELY cohortextractor image",
        "Updating OpenSAFELY python image",
        "Updating OpenSAFELY jupyter image",
        "Cleaning up old images",
    ]


def test_remove_deprecated_images(run):
    local_images = set(
        [
            "docker.opensafely.org/r",
            "ghcr.io/opensafely/r",
            "ghcr.io/opensafely-core/r",
        ]
    )

    run.expect(["docker", "image", "rm", "docker.opensafely.org/r"])
    run.expect(["docker", "image", "rm", "ghcr.io/opensafely/r"])

    pull.remove_deprecated_images(local_images)


def test_check_version_out_of_date(run, capsys):

    run.expect(
        ["docker", "images", "ghcr.io/opensafely-core/*", "--no-trunc", "--format={{.Repository}}={{.ID}}"], 
        stdout="ghcr.io/opensafely-core/python=sha256:oldsha"
    )

    assert len(pull.check_version()) == 1
    out, err = capsys.readouterr()
    assert err == ""
    assert out.splitlines() == [
        "Warning: the OpenSAFELY docker images for python actions are out of date - please update by running:",
        "    opensafely pull",
        "",
    ]


def test_check_version_up_to_date(run, capsys):

    current_sha = pull.get_remote_sha("ghcr.io/opensafely-core/python", "latest")
    pull.token = None

    run.expect(
        ["docker", "images", "ghcr.io/opensafely-core/*", "--no-trunc", "--format={{.Repository}}={{.ID}}"], 
        stdout=f"ghcr.io/opensafely-core/python={current_sha}"
    )

    assert len(pull.check_version()) == 0
    out, err = capsys.readouterr()
    assert err == ""
    assert out.splitlines() == []


@pytest.mark.parametrize(
    "project_yaml,exc_msg",
    [
        ("doesnotexist.yaml", "Could not find"),
        ("bad.yaml", "Could not parse"),
        ("noactions.yaml", "No actions found"),
    ],
)
def test_get_actions_from_project_yaml_errors(project_yaml, exc_msg):
    path = project_fixture_path / project_yaml
    with pytest.raises(RuntimeError) as exc_info:
        pull.get_actions_from_project_file(path)

    str_exc = str(exc_info.value).lower()
    assert exc_msg.lower() in str_exc
    assert str(path).lower() in str_exc


@pytest.mark.parametrize(
    "argv,expected",
    [
        ([], argparse.Namespace(image="all", force=False, project=None)),
        (["--force"], argparse.Namespace(image="all", force=True, project=None)),
        (["r"], argparse.Namespace(image="r", force=False, project=None)),
        (["r", "--force"], argparse.Namespace(image="r", force=True, project=None)),
        (
            ["--project", "project.yaml"],
            argparse.Namespace(image="all", force=False, project="project.yaml"),
        ),
        (["invalid"], SystemExit()),
    ],
)
def test_pull_parser_valid(argv, expected, capsys):
    parser = argparse.ArgumentParser()
    pull.add_arguments(parser)
    if isinstance(expected, SystemExit):
        with pytest.raises(SystemExit):
            parser.parse_args(argv)
    else:
        assert parser.parse_args(argv) == expected
