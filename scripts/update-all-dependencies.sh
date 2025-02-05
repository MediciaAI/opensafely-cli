#!/bin/bash
set -eou pipefail

if [ $# -eq 0 ]; then
  # Default if no argument is to upgrade everything
  set -- --upgrade
fi

echo "Compiling vendor.txt from vendor.in with latest dependencies"
pip-compile "$@" vendor.in

# We can't (and don't want to) vendor this binary package but I can't find a
# way to prevent pip-tools from including it so we excise it here.
echo "Removing ruamel.yaml.clib dependency"
sed -i 's/^\(ruamel\.yaml\.clib\)/# \1/' vendor.txt

echo "Vendoring all dependencies"
vendoring sync -v
