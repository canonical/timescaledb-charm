#!/usr/bin/env python3

"""Subordinate charm for TimescaleDB."""
import os
from subprocess import PIPE, Popen, check_call, check_output

from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus


class TimescaleDB(CharmBase):
    """Subordinate charm for TimescaleDB."""

    state = StoredState

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)

    def _on_install(self, event):
        installed = getattr(self.state, "installed", False)
        if installed:
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
            check_call(["sudo", "apt-get", "update", "-qq"])
            check_call(
                ["sudo", "apt-get", "install", "-y", "apt-transport-https", "lsb-release", "wget"]
            )

            debs = ["loader-deb", "tools-deb", "deb"]
            deb_paths = []

            for i in range(len(debs)):
                try:
                    path = self.model.resources.fetch(debs[i])
                    deb_paths.append(path)
                except NameError:
                    self.framework.model.unit.status = BlockedStatus(
                        f"install failed: resource '{debs[i]}' not found"
                    )
                    event.defer()
                    return
                except ModelError:
                    pass

            if not deb_paths:
                self.framework.model.unit.status = MaintenanceStatus(
                    "installing TimescaleDB from third-party repo"
                )
                self._install_from_repo(event)
            elif len(deb_paths) == len(debs):
                for dp in deb_paths:
                    check_call(["sudo", "dpkg", "-i", dp])
            else:
                self.framework.model.unit.status = BlockedStatus(
                    "install failed: missing at least one of the resources ['deb', 'loader-deb', 'tools-deb']"
                )
                event.defer()
                return

            check_call(["timescaledb-tune", "-yes"])
            check_call(["sudo", "systemctl", "restart", "postgresql"])
            event.framework.model.unit.status = ActiveStatus()
            self.state.installed = True
        except Exception as e:
            event.framework.model.unit.status = BlockedStatus(f"install failed: {e}")
            event.defer()

    def _install_from_repo(self, event):
        # add apt repo to sources
        release = check_output(["lsb_release", "-c", "-s"]).decode("utf-8").rstrip("\n")
        ps = Popen(
            [
                "echo",
                f"deb https://packagecloud.io/timescale/timescaledb/ubuntu/ {release} main",
            ],
            stdout=PIPE,
        )
        check_call(["sudo", "tee", "/etc/apt/sources.list.d/timescaledb.list"], stdin=ps.stdout)
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

        check_call(["sudo", "apt-get", "install", "-y", f"timescaledb-2-postgresql-{pgver}"])

    def _on_upgrade_charm(self, event):
        installed = getattr(self.state, "installed", False)
        if not installed:
            self.on_install(event)
            return
        try:
            check_call(["sudo", "apt-get", "update", "-qq"])
            check_call(["sudo", "apt-get", "dist-upgrade", "-y"])
            event.framework.model.unit.status = ActiveStatus()
        except Exception as e:
            event.framework.model.unit.status = BlockedStatus(f"upgrade failed: {e}")
            event.defer()


if __name__ == "__main__":
    main(TimescaleDB)
