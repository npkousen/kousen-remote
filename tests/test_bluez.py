from __future__ import annotations

import asyncio
import unittest

from kousen_remote.discovery.bluez import BlueZClient, BlueZUnavailable


class BlueZOperationTimeoutTests(unittest.TestCase):
    def test_operation_timeout_mentions_bluetoothctl_fallback(self) -> None:
        async def run() -> None:
            client = BlueZClient()
            await client._run_operation("pairing", "pair", asyncio.sleep(1), 0.001)

        with self.assertRaises(BlueZUnavailable) as raised:
            asyncio.run(run())

        message = str(raised.exception)
        self.assertIn("Timed out while pairing", message)
        self.assertIn("bluetoothctl pair <address>", message)


if __name__ == "__main__":
    unittest.main()
