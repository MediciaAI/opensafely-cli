import dataclasses
import datetime
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

# from opensafely._vendor import requests
import requests

DESCRIPTION = "Commands for interacting with https://codelists.opensafely.org/"

CODELISTS_DIR = "codelists"
CODELISTS_FILE = "codelists.txt"
MANIFEST_FILE = "codelists.json"


def add_arguments(parser):
    def show_help(**kwargs):
        parser.print_help()
        parser.exit()

    # Show help by default if no command supplied
    parser.set_defaults(function=show_help)
    subparsers = parser.add_subparsers(
        title="available commands", description="", metavar="COMMAND"
    )

    parser_update = subparsers.add_parser(
        "update",
        help=(
            f"Update codelists, using specification at "
            f"{CODELISTS_DIR}/{CODELISTS_FILE}"
        ),
    )
    parser_update.set_defaults(function=update)

    parser_check = subparsers.add_parser(
        "check",
        help=(
            f"Check that codelists on disk match the specification at "
            f"{CODELISTS_DIR}/{CODELISTS_FILE}"
        ),
    )
    parser_check.set_defaults(function=check)


# Just here for consistency so we can always reference `<module>.main()` in the
# primary entrypoint. The behaviour usually implemented by `main()` is handled
# by the default `show_help` above
def main():
    pass


def update(codelists_dir=None):
    if not codelists_dir:
        codelists_dir = Path.cwd() / CODELISTS_DIR
    codelists = parse_codelist_file(codelists_dir)
    old_files = set(codelists_dir.glob("*.csv"))
    new_files = set()
    manifest = {"files": {}}
    for codelist in codelists:
        print(f"Fetching {codelist.id}")
        try:
            response = requests.get(codelist.download_url)
            response.raise_for_status()
        except Exception as e:
            exit_with_error(
                f"Error downloading codelist: {e}\n\n"
                f"Check that you can access the codelist at:\n{codelist.url}"
            )
        codelist.filename.write_bytes(response.content)
        new_files.add(codelist.filename)
        key = str(codelist.filename.relative_to(codelists_dir))
        manifest["files"][key] = {
            "id": codelist.id,
            "url": codelist.url,
            "downloaded_at": f"{datetime.datetime.utcnow()}Z",
            "sha": hash_bytes(response.content),
        }
    manifest_file = codelists_dir / MANIFEST_FILE
    preserve_download_dates(manifest, manifest_file)
    manifest_file.write_text(json.dumps(manifest, indent=2))
    for file in old_files - new_files:
        print(f"Deleting {file.name}")
        file.unlink()
    return True


def check():
    codelists_dir = Path.cwd() / CODELISTS_DIR
    if not codelists_dir.exists():
        print(f"No '{CODELISTS_DIR}' directory present so nothing to check")
        return True
    codelists = parse_codelist_file(codelists_dir)
    manifest_file = codelists_dir / MANIFEST_FILE
    if not manifest_file.exists():
        # This is here so that switching to use this test in Github Actions
        # doesn't cause existing repos which previously passed to start
        # failing. It works by creating a temporary manifest file and then
        # checking against that. Functionally, this is the same as the old test
        # which would check against the OpenCodelists website every time.
        if os.environ.get("GITHUB_WORKFLOW"):
            print(
                "==> WARNING\n"
                "    Using temporary workaround for Github Actions tests.\n"
                "    You should run: opensafely codelists update\n"
            )
            manifest = make_temporary_manifest(codelists_dir)
        else:
            exit_with_prompt(f"No file found at '{CODELISTS_DIR}/{MANIFEST_FILE}'.")
    else:
        try:
            manifest = json.loads(manifest_file.read_text())
        except json.decoder.JSONDecodeError:  
            exit_with_prompt(
                f"'{CODELISTS_DIR}/{MANIFEST_FILE}' is invalid.\n"
                "Note that this file is automatically generated and should not be manually edited.\n"
            )
    all_ids = {codelist.id for codelist in codelists}
    ids_in_manifest = {f["id"] for f in manifest["files"].values()}
    if all_ids != ids_in_manifest:
        diff = format_diff(all_ids, ids_in_manifest)
        exit_with_prompt(
            f"It looks like '{CODELISTS_FILE}' has been edited but "
            f"'update' hasn't been run.\n{diff}\n"
        )
    all_csvs = set(f.name for f in codelists_dir.glob("*.csv"))
    csvs_in_manifest = set(manifest["files"].keys())
    if all_csvs != csvs_in_manifest:
        diff = format_diff(all_csvs, csvs_in_manifest)
        exit_with_prompt(
            f"It looks like CSV files have been added or deleted in the "
            f"'{CODELISTS_DIR}' folder.\n{diff}\n"
        )
    modified = []
    for filename, details in manifest["files"].items():
        csv_file = codelists_dir / filename
        sha = hash_bytes(csv_file.read_bytes())
        if sha != details["sha"]:
            modified.append(f"  {CODELISTS_DIR}/{filename}")
    if modified:
        exit_with_prompt(
            "A CSV file seems to have been modified since it was downloaded:\n"
            "{}\n".format("\n".join(modified))
        )
    print("Codelists OK")
    return True


def make_temporary_manifest(codelists_dir):
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        contents = codelists_dir.joinpath(CODELISTS_FILE).read_bytes()
        tmpdir.joinpath(CODELISTS_FILE).write_bytes(contents)
        update(codelists_dir=tmpdir)
        manifest = json.loads(tmpdir.joinpath(MANIFEST_FILE).read_text())
    return manifest


@dataclasses.dataclass
class Codelist:
    id: str
    url: str
    download_url: str
    filename: Path


def parse_codelist_file(codelists_dir):
    if not codelists_dir.exists() or not codelists_dir.is_dir():
        exit_with_error(f"No '{CODELISTS_DIR}' folder found")
    codelists_file = codelists_dir / CODELISTS_FILE
    if not codelists_file.exists():
        exit_with_error(f"No file found at '{CODELISTS_DIR}/{CODELISTS_FILE}'")
    codelists = []
    for line in codelists_file.read_text().splitlines():
        line = line.strip().rstrip("/")
        if not line or line.startswith("#"):
            continue
        tokens = line.split("/")
        if len(tokens) not in [3, 4]:
            exit_with_error(
                f"{line} does not match [project]/[codelist]/[version] "
                "or user/[username]/[codelist]/[version]"
            )
        url = f"https://codelists.opensafely.org/codelist/{line}/"
        filename = "-".join(tokens[:-1]) + ".csv"
        codelists.append(
            Codelist(
                id=line,
                url=url,
                download_url=f"{url}download.csv",
                filename=codelists_dir / filename,
            )
        )
    return codelists


def preserve_download_dates(manifest, old_manifest_file):
    """
    If file contents are unchanged then we copy the original download date from
    the existing manifest. This makes the update process idempotent and
    prevents unnecessary diff noise.
    """
    if not old_manifest_file.exists():
        return
    old_manifest = json.loads(old_manifest_file.read_text())
    for filename, details in manifest["files"].items():
        old_details = old_manifest["files"].get(filename)
        if old_details and old_details["sha"] == details["sha"]:
            details["downloaded_at"] = old_details["downloaded_at"]


def hash_bytes(content):
    # Normalize line-endings. Windows in general, and git on Windows in
    # particular, is prone to messing about with these
    content = b"\n".join(content.splitlines())
    return hashlib.sha1(content).hexdigest()


def format_diff(set_a, set_b):
    return "\n".join(
        [
            f"  {'  added' if element in set_a else 'removed'}: {element}"
            for element in set_a.symmetric_difference(set_b)
        ]
    )


def exit_with_prompt(message):
    exit_with_error(
        f"{message}\n"
        f"To fix these errors run the command below and commit the changes:\n\n"
        f"  opensafely codelists update\n"
    )


def exit_with_error(message):
    print(message)
    sys.exit(1)
