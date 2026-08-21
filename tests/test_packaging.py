from __future__ import annotations

import unittest
from pathlib import Path


class SystemdPackagingTests(unittest.TestCase):
    def test_service_uses_opt_venv_and_environment_file(self) -> None:
        service = Path("packaging/systemd/kousen-remote.service").read_text(encoding="utf-8")

        self.assertIn("EnvironmentFile=/etc/default/kousen-remote", service)
        self.assertIn("/opt/kousen-remote/.venv/bin/kousen-remote run", service)
        self.assertIn("--reconnect-delay", service)

    def test_default_file_points_to_installed_mapping(self) -> None:
        defaults = Path("packaging/systemd/kousen-remote.default").read_text(encoding="utf-8")

        self.assertIn("KOUSEN_REMOTE_DEVICE=", defaults)
        self.assertIn("KOUSEN_REMOTE_DEVICE=XX:XX:XX:XX:XX:XX", defaults)
        self.assertIn("KOUSEN_REMOTE_MAPPING=/opt/kousen-remote/mappings/kiosk-browser.json", defaults)

    def test_installer_documents_system_paths(self) -> None:
        installer = Path("packaging/systemd/install-systemd.sh").read_text(encoding="utf-8")

        self.assertIn("/opt/kousen-remote", installer)
        self.assertIn("/etc/default/kousen-remote", installer)
        self.assertIn("/etc/systemd/system/kousen-remote.service", installer)
        self.assertIn("--mapping", installer)
        self.assertIn("mappings/${mapping}.json", installer)


if __name__ == "__main__":
    unittest.main()
