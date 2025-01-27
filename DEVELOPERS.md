# Developer docs

## Vendoring

To minimise the possibility for installation issues this package vendors
all its dependencies under the [opensafely._vendor](./opensafely/_vendor)
namespace using the [vendoring](https://pypi.org/project/vendoring/) tool.

This brings its own complexities (particularly around the `requests`
package) but they are at least complexities which show up at development
time rather than on some researcher's mysteriously broken Python
installation.

The tool makes the process relatively painless. There are a few
workarounds (crude string subsitutions) we need to apply which are all
configured in [pyproject.toml](./pyproject.toml).

To update the vendored version of job-runner:

1. Install the developer tooling (you'll need Python 3.8 for this):
   ```
   pip install -r requirements.dev.txt
   ```

2. Run the update script:
   ```
   ./scripts/update-jobrunner.sh
   ```

3. Commit the results

4. If you want to update jobrunner's transitive dependencies you can use
   the update-all script, but this might require more work to get the
   vendoring working successfully:
    ```
    ./scripts/update-all-dependencies.sh
    ```

## Tests

Test with:
```
python -m pytest
```

Due to the fact that we're vendoring `requests` there's some slightly
nasty monkeypatching which we need to apply `requests_mock` in order to
get it to mock the right library. Monkeypatching mocking libraries is
known as "software engineering".
