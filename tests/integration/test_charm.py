#!/usr/bin/env python3

import logging
import re
from pathlib import Path

import pytest
import yaml
from juju.errors import JujuError
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
APP_NAME = METADATA["name"]


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    # Build and deploy charm from local source folder.
    charm = await ops_test.build_charm(".")

    # Test that the charm is a subordinate, adding multiple units should fail.
    with pytest.raises(JujuError):
        await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=100)

    # Deploy the charm.
    await ops_test.model.deploy(charm, application_name=APP_NAME, num_units=0)

    # Deploy postgresql charm.
    await ops_test.model.deploy("postgresql", series="focal")
    await ops_test.model.wait_for_idle(
        apps=["postgresql"], status="active", raise_on_blocked=True, timeout=1000
    )

    # Integrate the timescaledb charm with postgresql.
    await ops_test.model.integrate(APP_NAME, "postgresql")
    await ops_test.model.wait_for_idle(
        apps=[APP_NAME], status="active", raise_on_blocked=True, timeout=1000
    )

    # Create database, activate TimescaleDB and check that it is enabled.
    ret = await ops_test.juju(
        "ssh",
        "postgresql/0",
        r'echo -e "CREATE DATABASE tdb;\\n \\\c tdb;\\n CREATE EXTENSION IF NOT EXISTS timescaledb;\\n \\\dx;" | sudo psql -U postgres -f -',
    )

    extension_regex = r"timescaledb\s*\|\s*.+\s*\|\s*public\s*\|\s*Enables scalable inserts and complex queries for time-series data"
    assert re.search(extension_regex, ret[1])
