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
        self.framework.observe(self.on.config_changed, self._on_config_changed)
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
            self.state.installed = True
        except Exception as e:
            event.framework.model.unit.status = BlockedStatus(f"install failed: {e}")
            event.defer()

    def _remove_repo(self, event):
        return

    def _install_from_resources(self, event):
        debs = ["loader-deb", "tools-deb", "deb"]
        deb_paths = []

        try:
            deb_paths = [self.model.resources.fetch(d) for d in debs]
        except (NameError, ModelError) as e:
            self.framework.model.unit.status = BlockedStatus(
                f"install failed: cannot load resource: {e}"
            )
            event.defer()
            return

        for dp in deb_paths:
            check_call(["sudo", "dpkg", "-i", dp])

    # setup apt repository
    def _setup_repo(self, event):
        # add apt repo to sources
        apt_repo = self.state.config["apt_repository"]
        release = check_output(["lsb_release", "-c", "-s"]).decode("utf-8").rstrip("\n")
        ps = Popen(
            [
                "echo",
                f"deb {apt_repo} {release} main",
            ],
            stdout=PIPE,
        )
        check_call(["sudo", "tee", "/etc/apt/sources.list.d/timescaledb.list"], stdin=ps.stdout)
        ps.wait()

        # add apt key
        apt_key = self.state.config["apt_key"]
        if apt_key:
            ps = Popen(
                [
                    "wget",
                    "--quiet",
                    "-O",
                    "-",
                    apt_key,
                ],
                stdout=PIPE,
            )
            check_call(["sudo", "apt-key", "add", "-"], stdin=ps.stdout)
            ps.wait()

    # install TimescaleDB from apt repository
    def _install_from_repo(self, event):
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

        tsdb = f"timescaledb-2-postgresql-{pgver}"
        tsdb_loader = f"timescaledb-2-postgresql-{pgver}"
        ver = self.state.config["version"]
        if ver:
            tsdb = f"{tsdb}={ver}"
            tsdb_loader = f"{tsdb_loader}={ver}"

        check_call(["sudo", "apt-get", "install", "-y", tsdb, tsdb_loader])

    # handle configuration changes
    def _on_config_changed(self, event):
        event.framework.model.unit.status = MaintenanceStatus("setting up TimescaleDB per config")

        old_config = getattr(self.state, "config", None)
        new_config = {
            "from_resources": event.framework.model.config["from-resources"],
            "apt_key": event.framework.model.config["apt-key"],
            "apt_repository": event.framework.model.config["apt-repository"],
            "version": event.framework.model.config["version"],
        }
        self.state.config = new_config

        if old_config:
            # if we have an old config, it means this is a config change after initial setup
            if new_config["from_resources"] != old_config["from_resources"]:
                # we don't support changing 'from-resource' config post-setup
                self.framework.model.unit.status = BlockedStatus(
                    "config failed: cannot change from-resource value after TimescaleDB was setup"
                )

            if not new_config["from_resources"]:
                if (
                    old_config["apt_repository"] != new_config["apt_repository"]
                    or old_config["apt_key"] != new_config["apt_key"]
                ):
                    self._setup_repo(event)
                    self._install_from_repo(event)
                elif old_config["version"] != new_config["version"]:
                    self._install_from_repo(event)
            else:
                event.framework.model.unit.status = ActiveStatus()
                return
        else:
            # no old config, this is the first setup
            if new_config["from_resources"]:
                self._install_from_resources(event)
            else:
                self._setup_repo(event)
                self._install_from_repo(event)

        # setup timescaledb after installation
        check_call(["timescaledb-tune", "-yes"])
        check_call(["sudo", "systemctl", "restart", "postgresql"])

        event.framework.model.unit.status = ActiveStatus()

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
