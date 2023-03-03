#!/usr/bin/env python3

"""Subordinate charm for TimescaleDB."""
import os
from subprocess import PIPE, Popen, check_call, check_output

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus


class TimescaleDB(CharmBase):
    """Subordinate charm for TimescaleDB."""

    state = StoredState

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)

    def _on_install(self, event):
        if not hasattr(self.state, "installed"):
            self.state.installed = False
        elif self.state.installed:
            return
        try:
            # test if postgresql installed yet
            if not os.path.exists("/var/lib/postgresql"):
                event.framework.model.unit.status = WaitingStatus(
                    "waiting for postgresql to be installed"
                )
                event.defer()
                return

            # install dependencies
            check_call(
                ["sudo", "apt-get", "install", "-y", "apt-transport-https", "lsb-release", "wget"]
            )

            # add apt repo to sources
            release = check_output(["lsb_release", "-c", "-s"]).decode("utf-8").rstrip("\n")
            ps = Popen(
                [
                    "echo",
                    "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ {} main".format(
                        release
                    ),
                ],
                stdout=PIPE,
            )
            check_call(
                ["sudo", "tee", "/etc/apt/sources.list.d/timescaledb.list"], stdin=ps.stdout
            )
            ps.wait()

            # add apt key
            ps = Popen(
                [
                    "wget",
                    "--quiet",
                    "-O",
                    "-",
                    "https://packagecloud.io/timescale/timescaledb/gpgkey",
                ],
                stdout=PIPE,
            )
            check_call(["sudo", "apt-key", "add", "-"], stdin=ps.stdout)
            ps.wait()

            # install TimescaleDB
            check_call(["sudo", "apt-get", "update", "-qq"])

            if os.path.exists("/var/lib/postgresql/12"):
                pgver = 12
            elif os.path.exists("/var/lib/postgresql/14"):
                pgver = 14
            else:
                event.framework.model.unit.status = BlockedStatus(
                    "failed to find a compatible version of postgresql (12, 14)"
                )
                event.defer()
                return

            check_call(
                ["sudo", "apt-get", "install", "-y", "timescaledb-2-postgresql-{}".format(pgver)]
            )
            check_call(["timescaledb-tune", "-yes"])
            check_call(["sudo", "systemctl", "restart", "postgresql"])
            event.framework.model.unit.status = ActiveStatus()
            self.state.installed = True
        except Exception as e:
            event.framework.model.unit.status = BlockedStatus("{}: {}".format("install failed", e))
            event.defer()

    def _on_upgrade_charm(self, event):
        if not hasattr(self.state, "installed"):
            self.on_install(event)
            return
        try:
            check_call(["sudo", "apt-get", "update", "-qq"])
            check_call(["sudo", "apt-get", "dist-upgrade", "-y"])
            event.framework.model.unit.status = ActiveStatus()
        except Exception as e:
            event.framework.model.unit.status = BlockedStatus("{}: {}".format("upgrade failed", e))
            event.defer()


if __name__ == "__main__":
    main(TimescaleDB)
