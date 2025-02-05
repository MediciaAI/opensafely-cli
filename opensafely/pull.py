import subprocess
import sys
from http.cookiejar import split_header_words
from pathlib import Path
from urllib.parse import urlparse

# from opensafely._vendor import requests
import requests

from opensafely._vendor.jobrunner import config
from opensafely._vendor.jobrunner.cli.local_run import docker_preflight_check

# from opensafely._vendor.ruamel.yaml import YAML
from ruamel.yaml import YAML

from ruamel.yaml.error import (YAMLError, YAMLFutureWarning,
                               YAMLStreamError, YAMLWarning)
# from opensafely._vendor.ruamel.yaml.error import (YAMLError, YAMLFutureWarning,
#                                                   YAMLStreamError, YAMLWarning)

DESCRIPTION = (
    "Command for updating the docker images used to run MediciaSAFELY studies locally"
)
REGISTRY = config.DOCKER_REGISTRY
IMAGES = list(config.ALLOWED_IMAGES)
FULL_IMAGES = {f"{REGISTRY}/{image}" for image in IMAGES}
DEPRECATED_REGISTRIES = ["docker.opensafely.org", "ghcr.io/opensafely"]
IMAGES.sort()  # this is just for consistency for testing


def add_arguments(parser):
    choices = ["all"] + IMAGES
    parser.add_argument(
        "image",
        nargs="?",
        choices=choices,
        help="MediciaSAFELY docker image to update (default: all)",
        default="all",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Update docker images even if not present locally",
    )
    parser.add_argument(
        "--project",
        help="Use this project to yaml to decide which images to download",
    )


def main(image="all", force=False, project=None):
    if not docker_preflight_check():
        return False

    if project:
        force = True
        images = get_actions_from_project_file(project)
    elif image == "all":
        images = IMAGES
    else:
        # if user has requested a specific image, pull it regardless
        force = True
        images = [image]

    local_images = get_local_images()
    try:
        updated = False
        for image in images:
            # currently databuilder is not published, so we ignore it when pulling
            if image == "databuilder":
                continue
            tag = f"{REGISTRY}/{image}"
            if force or tag in local_images:
                updated = True
                print(f"Updating MediciaSAFELY {image} image")
                subprocess.run(["docker", "pull", tag + ":latest"], check=True)

        if updated:
            print("Cleaning up old images")
            remove_deprecated_images(local_images)
            subprocess.run(["docker", "image", "prune", "--force"], check=True)
        else:
            print("No MediciaSAFELY docker images found to update.")

    except subprocess.CalledProcessError as exc:
        sys.exit(exc.stderr)


def get_actions_from_project_file(project_yaml):
    path = Path(project_yaml)
    if not path.exists():
        raise RuntimeError(f"Could not find {project_yaml}")

    try:
        with path.open() as f:
            project = YAML(typ="safe", pure=True).load(path)
    except (YAMLError, YAMLStreamError, YAMLWarning, YAMLFutureWarning) as e:
        raise RuntimeError(f"Could not parse {project_yaml}: str(e)")

    images = []
    for action_name, action in project.get("actions", {}).items():
        if not action:
            continue
        command = action.get("run", None)
        if command is None:
            continue

        name, _, version = command.partition(":")
        if name in IMAGES:
            images.append(name)

    if not images:
        raise RuntimeError(f"No actions found in {project_yaml}")

    return images


def get_local_images():
    """Returns a dict of locally installed MediciaSAFELY images and their SHA."""
    ps = subprocess.run(
        [
            "docker",
            "images",
            "ghcr.io/mediciaai/*",
            "--no-trunc",
            "--format={{.Repository}}={{.ID}}",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    lines = [line for line in ps.stdout.splitlines() if line.strip()]
    all_images = dict(l.split("=", 1) for l in lines)
    return {k: v for k, v in all_images.items() if k in FULL_IMAGES}


def remove_deprecated_images(local_images):
    """Temporary clean up functon to remove orphaned images."""
    for registry in DEPRECATED_REGISTRIES:
        for image in IMAGES:
            tag = f"{registry}/{image}"
            if tag in local_images:
                subprocess.run(["docker", "image", "rm", tag], capture_output=True)


session = requests.Session()
token = None


def get_remote_sha(full_name, tag):
    """Get the current sha for a tag from a docker registry."""
    global token

    parsed = urlparse("https://" + full_name)
    manifest_url = f"https://ghcr.io/v2/{parsed.path}/manifests/{tag}"

    if token is None:
        # Docker API requires auth token, even for public resources.
        # However, we can reuse a public token.
        response = session.get(manifest_url)
        token = get_auth_token(response.headers["www-authenticate"])

    response = session.get(manifest_url, headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return response.json()["config"]["digest"]


def get_auth_token(header):
    """Parse a docker v2 www-authentication header and fetch a token.

    Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:mediciaai/busybox:pull"
    """
    header = header.lstrip("Bearer")
    # split_header_words is weird, but better than doing it ourselves
    words = split_header_words([header])
    values = dict(next(zip(*words)))
    url = values.pop("realm")
    auth_response = session.get(url, params=values)
    return auth_response.json()["token"]


def check_version():
    need_update = []
    local_images = get_local_images()

    for image in IMAGES:
        full_name = f"{REGISTRY}/{image}"
        local_sha = local_images.get(full_name)
        if local_sha is None:
            continue
        if local_sha != get_remote_sha(full_name, "latest"):
            need_update.append(image)

    if need_update:
        print(
            f"Warning: the MediciaSAFELY docker images for {', '.join(need_update)} actions are out of date - please update by running:\n"
            "    opensafely pull\n"
        )
    return need_update
