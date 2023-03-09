# Copyright 2023 Canonical
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import subprocess
from unittest import TestCase
from unittest.mock import ANY, MagicMock, call, patch

from charm import TimescaleDB
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness


class TestCharm(TestCase):
    @patch("os.path.exists")
    def test_waiting_for_postgresql(self, mock_exists):
        """Waits for Postgresql to be set up."""
        harness = Harness(TimescaleDB)
        self.addCleanup(harness.cleanup)

        mock_exists.return_value = False
        harness.begin()
        harness.charm.on.install.emit()
        mock_exists.assert_called_with("/var/lib/postgresql")
        self.assertEqual(
            harness.model.unit.status, WaitingStatus("waiting for postgresql to be installed")
        )

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    @patch("subprocess.check_call")
    @patch("subprocess.check_output")
    def test_install_from_repository(
        self, mock_check_output, mock_check_call, mock_popen, mock_exists
    ):
        """Installs fine from repository when all is good."""
        harness = Harness(
            TimescaleDB,
            config="""
            options:
                apt-repository:
                  default: https://packagecloud.io/timescale/timescaledb/ubuntu/
                  type: string
                apt-key:
                  default:
                  type: string
                version:
                  default:
                  type: string
        """,
        )
        self.addCleanup(harness.cleanup)

        mock_popen_pipe = MagicMock(spec=subprocess.Popen)
        mock_popen_pipe.stdout = MagicMock(spec=subprocess.PIPE)
        mock_popen_pipe.wait = MagicMock()
        mock_popen_pipe.wait.return_value = None
        mock_popen.return_value = mock_popen_pipe
        mock_check_call.return_value = None
        mock_check_output.return_value = "focal".encode()
        mock_exists.return_value = True

        harness.begin()
        harness.charm.on.install.emit()

        mock_exists.assert_has_calls([call("/var/lib/postgresql"), call("/var/lib/postgresql/12")])
        mock_popen.assert_called_once_with(
            [
                "echo",
                "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ focal main",
            ],
            stdout=subprocess.PIPE,
        )
        mock_check_call.assert_has_calls(
            [
                call(["sudo", "apt-get", "update", "-qq"]),
                call(
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
                ),
                call(
                    ["sudo", "tee", "/etc/apt/sources.list.d/timescaledb.list"],
                    stdin=mock_popen_pipe.stdout,
                ),
                call(["sudo", "apt-get", "update", "-qq"]),
                call(
                    [
                        "sudo",
                        "apt-get",
                        "install",
                        "-y",
                        "timescaledb-2-postgresql-12",
                        "timescaledb-2-loader-postgresql-12",
                    ]
                ),
                call(["timescaledb-tune", "-yes"]),
                call(["sudo", "systemctl", "restart", "postgresql"]),
            ]
        )
        self.assertEqual(harness.model.unit.status, ActiveStatus())

        # Verify that config_changed event does nothing if the config didn't meaningfully change.
        mock_check_call.reset_mock()
        mock_popen.reset_mock()
        mock_exists.reset_mock()
        harness.charm.on.config_changed.emit()
        mock_check_call.assert_not_called()
        mock_popen.assert_not_called()
        mock_exists.assert_not_called()
        self.assertEqual(harness.model.unit.status, ActiveStatus())

    @patch("os.path.exists")
    @patch("subprocess.Popen")
    @patch("subprocess.check_call")
    @patch("subprocess.check_output")
    def test_install_from_repository_fail_and_recovery(
        self, mock_check_output, mock_check_call, mock_popen, mock_exists
    ):
        """Install from repository fails if config is wrong, can be fixed via config update."""
        harness = Harness(
            TimescaleDB,
            config="""
            options:
                apt-repository:
                  default:
                  type: string
                apt-key:
                  default:
                  type: string
                version:
                  default:
                  type: string
        """,
        )
        self.addCleanup(harness.cleanup)

        mock_popen_pipe = MagicMock(spec=subprocess.Popen)
        mock_popen_pipe.stdout = MagicMock(spec=subprocess.PIPE)
        mock_popen_pipe.wait = MagicMock()
        mock_popen_pipe.wait.return_value = None
        mock_popen.return_value = mock_popen_pipe
        mock_check_call.return_value = None
        mock_check_output.return_value = "focal".encode()
        mock_exists.return_value = True

        harness.begin()
        harness.charm.on.install.emit()

        mock_exists.assert_has_calls([call("/var/lib/postgresql")])

        self.assertEqual(
            harness.model.unit.status, BlockedStatus("installation failed: 'apt-repository'")
        )

        # Fixing configuration works.
        harness.update_config(
            {
                "apt-repository": "https://packagecloud.io/timescale/timescaledb/ubuntu/",
                "apt-key": "",
                "version": "",
            }
        )
        mock_exists.assert_has_calls([call("/var/lib/postgresql"), call("/var/lib/postgresql/12")])
        mock_popen.assert_called_once_with(
            [
                "echo",
                "deb https://packagecloud.io/timescale/timescaledb/ubuntu/ focal main",
            ],
            stdout=subprocess.PIPE,
        )
        mock_check_call.assert_has_calls(
            [
                call(["sudo", "apt-get", "update", "-qq"]),
                call(
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
                ),
                call(
                    ["sudo", "tee", "/etc/apt/sources.list.d/timescaledb.list"],
                    stdin=mock_popen_pipe.stdout,
                ),
                call(["sudo", "apt-get", "update", "-qq"]),
                call(
                    [
                        "sudo",
                        "apt-get",
                        "install",
                        "-y",
                        "timescaledb-2-postgresql-12",
                        "timescaledb-2-loader-postgresql-12",
                    ]
                ),
                call(["timescaledb-tune", "-yes"]),
                call(["sudo", "systemctl", "restart", "postgresql"]),
            ]
        )
        self.assertEqual(harness.model.unit.status, ActiveStatus())

    @patch("os.path.exists")
    @patch("subprocess.check_call")
    @patch("subprocess.check_output")
    def test_install_from_resources(self, mock_check_output, mock_check_call, mock_exists):
        """Installs fine from resources when all is good and resources are provided."""
        harness = Harness(
            TimescaleDB,
            config="""
            options:
                apt-repository:
                  default: https://packagecloud.io/timescale/timescaledb/ubuntu/
                  type: string
                apt-key:
                  default:
                  type: string
                version:
                  default:
                  type: string
        """,
        )
        self.addCleanup(harness.cleanup)
        harness.add_resource("deb", "test-deb-content")
        harness.add_resource("loader-deb", "test-deb-content")
        harness.add_resource("tools-deb", "test-deb-content")

        mock_exists.return_value = True
        mock_check_call.return_value = None
        mock_check_output.return_value = "some_sha_sum".encode()

        harness.begin()
        harness.charm.on.install.emit()

        mock_check_call.assert_has_calls(
            [
                call(["sudo", "apt-get", "update", "-qq"]),
                call(
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
                ),
                call(["sudo", "dpkg", "-i", ANY]),
                call(["sudo", "dpkg", "-i", ANY]),
                call(["sudo", "dpkg", "-i", ANY]),
                call(["timescaledb-tune", "-yes"]),
                call(["sudo", "systemctl", "restart", "postgresql"]),
            ]
        )
        self.assertEqual(harness.model.unit.status, ActiveStatus())

        # Upgrade does not reinstall resources because they were not changed.
        mock_check_call.reset_mock()
        harness.charm.on.upgrade_charm.emit()
        mock_check_call.assert_not_called()

    @patch("os.path.exists")
    @patch("subprocess.check_call")
    @patch("subprocess.check_output")
    def test_install_from_resources_fail(self, mock_check_output, mock_check_call, mock_exists):
        """Install from resources fails when not all resources are provided."""
        harness = Harness(
            TimescaleDB,
            config="""
            options:
                apt-repository:
                  default: https://packagecloud.io/timescale/timescaledb/ubuntu/
                  type: string
                apt-key:
                  default:
                  type: string
                version:
                  default:
                  type: string
        """,
        )
        self.addCleanup(harness.cleanup)
        harness.add_resource("deb", "test-deb-content")
        harness.add_resource("loader-deb", "test-deb-content")

        mock_exists.return_value = True
        mock_check_call.return_value = None
        mock_check_output.return_value = "some_sha_sum".encode()

        harness.begin()
        harness.charm.on.install.emit()

        mock_check_call.assert_has_calls(
            [
                call(["sudo", "apt-get", "update", "-qq"]),
                call(
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
                ),
            ]
        )
        self.assertEqual(
            harness.model.unit.status,
            BlockedStatus("installation failed: resource missing: tools-deb"),
        )
