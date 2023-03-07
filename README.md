# TimescaleDB Subordinate Charm

## Description

TimescaleDB is an open-source database built for analyzing time-series data with the power and
convenience of SQL - on premise, at the edge or in the cloud. This repository offers a charmed
TimescaleDB that installs as a PostgreSQL extension. This charm is a subordinate to the main
postgresql charm that installs the extension and configures PostgreSQL to make it generally
available.

Please note that, by default, the charm will install the latest timescaledb version for the
corresponding postgres version, by pulling the built package directly from TimescaleDB's third
party apt repository as per [the Timescale documentation](https://docs.timescale.com/install/latest/self-hosted/installation-linux/).
The charm offers configuration options for a custom apt repository and/or TimescaleDB version.

Alternatively, the charm also offers the possibility to install from-resources. In this case, the
charm should be deployed directly with the `from-resources` config set to `True` and the resources
must be provided at install time (debs for `timescaledb-2-loader`, `timescaledb-2-postgresql` and
`timescaledb-tools`).

## Usage
In order to deploy the charm, one must have a postgresql charm deployed. Please note that this
charm does not work with the postresql-k8s charm.

```
# Create a model.
juju add-model dev
# Deploy a postgresql charm.
juju deploy postgresql
# Watch for the postgresql to be up and running.
juju status
# Deploy the timescaledb charm.
juju deploy timescaledb
# Relate the two charms together.
juju add-relation timescaledb postgresql
```

From this point, follow the general TimescaleDB instructions to enable TimescaleDB in individual
PostgreSQL databases.

Alternatively, the `juju deploy` step can be performed with custom resources:
```
juju deploy timescaledb --resource deb=<path-to-tsdb-deb> --resource loader-deb=<path-to-tsdb-loader> --resource tools-deb=<path-to-tsdb-tools>
```

## Contributing
Please refer to [CONTRIBUTING.md](CONTRIBUTING.md).

## License
The Charmed PostgreSQL Operator is free software, distributed under the Apache Software License,
version 2.0. See [LICENSE](LICENSE) for more information.
