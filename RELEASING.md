# Releasing `simple-skill-manager`

The package is published to [PyPI](https://pypi.org/project/simple-skill-manager/)
from GitHub Actions using **trusted publishing** (OIDC). No API token is
stored in the repository, and the workflow has no secrets to configure.

## One-time setup

This has already been done for this repository; the values are recorded
here so the setup can be reproduced or moved.

1. **PyPI account** with two-factor authentication enabled.
2. **Pending publisher** — because the project did not exist on PyPI when
   it was first published, it is registered as a *pending* publisher, which
   creates the project on the first upload:

   Account settings → **Publishing** → **GitHub Actions** → **Add**

   | Field | Value |
   | --- | --- |
   | PyPI project name | `simple-skill-manager` |
   | Owner | `tomjanus` |
   | Repository name | `skill-manager` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

   The workflow name must match the file name
   `.github/workflows/publish.yml`, and the environment name must match the
   `environment:` key in that workflow.

3. **GitHub environment** named `pypi` in the repository settings. It is
   where the publish job runs; it can be given required reviewers to
   approve each release before it is uploaded.

## Publishing a release

1. Update the version in `pyproject.toml` and add a `CHANGELOG.md` entry.

2. Commit and tag:

   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "release: v0.2.0"
   git tag -a v0.2.0 -m "v0.2.0"
   git push origin master --tags
   ```

3. The `publish.yml` workflow builds the sdist and the wheel and uploads
   them to PyPI. Watch it on the repository's **Actions** tab.

   Creating a GitHub release for the same tag also triggers the workflow;
   both triggers are safe to use because the upload skips versions that
   already exist on PyPI.

4. Verify:

   ```bash
   pipx install simple-skill-manager
   simple-skill-manager --help
   ```

   and check <https://pypi.org/project/simple-skill-manager/>.

## Publishing without GitHub Actions

If the workflow cannot be used, the same artifacts can be uploaded from a
machine with a PyPI API token:

1. Build the distribution:

   ```bash
   python -m build
   twine check dist/*
   ```

2. Upload with a token (scope: *pypi.org → project → simple-skill-manager*):

   ```bash
   TWINE_USERNAME=__token__ TWINE_PASSWORD=pypi-... twine upload dist/*
   ```

   The token can also be stored in `~/.pypirc`:

   ```ini
   [pypi]
   username = __token__
   password = pypi-...
   ```

   A token uploaded this way belongs to a PyPI user, so the maintainer
   account must be added as an owner of the project afterwards.

## Versioning

The project follows [Semantic Versioning](https://semver.org/). The version
in `pyproject.toml` must match the release tag, because the tag is what
identifies the release.
