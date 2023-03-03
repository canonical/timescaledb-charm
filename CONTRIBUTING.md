# Contributing

## Developing
The charm is entirely defined in `charm.py`.

You can run various operations with `tox`, e.g.:
```
# Format the code.
tox -e fmt
# Lint the code.
tox -e lint
# Run integration tests.
tox -e integration
```

## Building the charm
The charm can be build by running:
```
charmcraft pack
```

## Deploying the charm
In order to deploy the charm, one must have a [Postgresql charm] deployed.

```
# Create a model.
juju add-model dev
# Deploy a postgresql charm.
juju deploy postgresql
# Watch for the postgresql to be up and running.
juju status
# Deploy the timescaledb charm.
juju deploy ./timescaledb_ubuntu-20.04-amd64.charm
# Relate the two charms together.
juju integrate timescaledb postgresql
```
