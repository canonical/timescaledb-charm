#!/usr/bin/env python3

"""Subordinate charm for TimescaleDB."""
import os
import subprocess

# from subprocess import subprocess.PIPE, subprocess.Popen, subprocess.check_call, subprocess.check_output
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus


class TimescaleDB(CharmBase):
    """Subordinate charm for TimescaleDB."""

    _stored = StoredState()
    _debs = ["loader-deb", "tools-deb", "deb"]

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self._stored.set_default(installed=False)
        self._stored.set_default(has_resources=False)
        self._stored.set_default(config={})

    # Install hook that installs TimescaleDB.
    def _on_install(self, event):
        if self._stored.installed:
            return
        try:
            # test if postgresql installed yet
            if not os.path.exists("/var/lib/postgresql"):
                event.framework.model.unit.status = WaitingStatus(
                    "waiting for postgresql to be installed"
                )
                event.defer()
                return

            self._setup_dependencies()

            # if resources provided, set up from resource, otherwise from config
            deb_paths = self._get_resource_paths()
            if deb_paths:
                self._stored.has_resources = True
                self._setup_from_resources(deb_paths)
            else:
                config = self._get_config(event)
                self._setup_repo(config)
                self._setup_from_repo(config)
                self._stored.config = config

            self._stored.installed = True
            event.framework.model.unit.status = ActiveStatus()
        except Exception as e:
            event.framework.model.unit.status = BlockedStatus(f"installation failed: {e}")
            event.defer()

    # Config_changed hook that sets up TimescaleDB according to the configuration of the charm.
    # It will only work if the charm is not set up using resources.
    def _on_config_changed(self, event):
        # if we set up from resources, skip the event
        if self._stored.has_resources:
            return

        event.framework.model.unit.status = MaintenanceStatus("setting up TimescaleDB per config")
        try:
            old_config = self._stored.config
            new_config = self._get_config(event)

            if not old_config or (
                old_config["apt_repository"] != new_config["apt_repository"]
                or old_config["apt_key"] != new_config["apt_key"]
            ):
                self._setup_repo(new_config)
                self._setup_from_repo(new_config)
            elif old_config and old_config["version"] != new_config["version"]:
                self._setup_from_repo(new_config)

            self._stored.config = new_config
            event.framework.model.unit.status = ActiveStatus()
        except Exception as e:
            event.framework.model.unit.status = BlockedStatus(f"config change failed: {e}")
            event.defer()

    # Upgrade hook that will upgrade the TimescaleDB packages, depending on the setup method.
    def _on_upgrade_charm(self, event):
        event.framework.model.unit.status = MaintenanceStatus("upgrading charm")
        try:
            if self._stored.has_resources:
                self._setup_from_resources(self._get_resource_paths())
            else:
                subprocess.check_call(["sudo", "apt-get", "update", "-qq"])
                subprocess.check_call(["sudo", "apt-get", "dist-upgrade", "-y"])

            event.framework.model.unit.status = ActiveStatus()
        except Exception as e:
            event.framework.model.unit.status = BlockedStatus(f"upgrade failed: {e}")
            event.defer()

    # Helper to get the configurations of the charm.
    def _get_config(self, event):
        return {
            "apt_key": event.framework.model.config.get("apt-key", ""),
            "apt_repository": event.framework.model.config["apt-repository"],
            "version": event.framework.model.config.get("version", ""),
        }

    # Helper to setup the dependencies required by TimescaleDB.
    def _setup_dependencies(self):
        subprocess.check_call(["sudo", "apt-get", "update", "-qq"])
        subprocess.check_call(
            [
                "sudo",
                "apt-get",
                "install",
                "-y",
                "coreutils",
                "apt-transport-https",
                "lsb-release",
                "wget",
            ]
        )

    # Helper to get the deb paths expected by the charm.
    def _get_resource_paths(self):
        deb_paths = {}
        for d in self._debs:
            try:
                deb_paths[d] = self.model.resources.fetch(d)
            except (NameError, ModelError):
                pass

        return deb_paths

    # Helper to setup TimescaleDB from the given deb paths.
    def _setup_from_resources(self, deb_paths):
        for d in self._debs:
            if not deb_paths.get(d, ""):
                raise Exception(f"resource missing: {d}")

        rh = getattr(self._stored, "resource_hashes", {})
        changed = False
        for d in self._debs:
            old_hash = rh.get(d, "")
            new_hash = (
                subprocess.check_output(["sha1sum", deb_paths[d]]).decode("utf-8").split()[0]
            )
            rh[d] = new_hash

            if old_hash != new_hash:
                subprocess.check_call(["sudo", "dpkg", "-i", deb_paths[d]])
                changed = True

        if changed:
            subprocess.check_call(["timescaledb-tune", "-yes"])
            subprocess.check_call(["sudo", "systemctl", "restart", "postgresql"])
            self._stored.resource_hashes = rh

    # Helper to setup the apt repository for TimescaleDB.
    def _setup_repo(self, config):
        # add apt repo to sources
        apt_repo = config["apt_repository"]
        release = subprocess.check_output(["lsb_release", "-c", "-s"]).decode("utf-8").rstrip("\n")
        ps = subprocess.Popen(
            [
                "echo",
                f"deb {apt_repo} {release} main",
            ],
            stdout=subprocess.PIPE,
        )
        subprocess.check_call(
            ["sudo", "tee", "/etc/apt/sources.list.d/timescaledb.list"], stdin=ps.stdout
        )
        ps.wait()

        # add apt key
        apt_key = config["apt_key"]
        if apt_key:
            ps = subprocess.Popen(
                [
                    "wget",
                    "--quiet",
                    "-O",
                    "-",
                    apt_key,
                ],
                stdout=subprocess.PIPE,
            )
            subprocess.check_call(["sudo", "apt-key", "add", "-"], stdin=ps.stdout)
            ps.wait()

    # Helper to setup TimescaleDB from a previously added apt repository. If TimescaleDB is
    # already setup, it will update it, assuming the version pointed by the config is an update
    # of the existing one.
    def _setup_from_repo(self, config):
        subprocess.check_call(["sudo", "apt-get", "update", "-qq"])
        if os.path.exists("/var/lib/postgresql/12"):
            pgver = 12
        elif os.path.exists("/var/lib/postgresql/14"):
            pgver = 14
        else:
            raise Exception("failed to find a compatible version of postgresql (12, 14)")

        tsdb = f"timescaledb-2-postgresql-{pgver}"
        tsdb_loader = f"timescaledb-2-loader-postgresql-{pgver}"
        ver = config["version"]
        if ver:
            tsdb = f"{tsdb}={ver}"
            tsdb_loader = f"{tsdb_loader}={ver}"

        subprocess.check_call(["sudo", "apt-get", "install", "-y", tsdb, tsdb_loader])
        subprocess.check_call(["timescaledb-tune", "-yes"])
        subprocess.check_call(["sudo", "systemctl", "restart", "postgresql"])


if __name__ == "__main__":
    main(TimescaleDB)
