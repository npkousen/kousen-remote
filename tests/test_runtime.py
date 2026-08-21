from __future__ import annotations

import io
import time
import unittest

from kousen_remote.mapping import MappingConfig, NormalizedAction
from kousen_remote.service.runtime import ActionDispatcher, RuntimeConfig, create_output, _remaining_timeout


class FakeOutput:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def press_key(self, key_code: str) -> None:
        self.events.append(("press", key_code))

    def release_key(self, key_code: str) -> None:
        self.events.append(("release", key_code))

    def close(self) -> None:
        self.events.append(("close", ""))


class RuntimeDispatcherTests(unittest.TestCase):
    def test_press_and_release_mapped_action(self) -> None:
        output = FakeOutput()
        dispatcher = ActionDispatcher(mapping=MappingConfig.default(), output=output, stream=io.StringIO())

        dispatcher.handle_payload(bytes.fromhex("0002"))
        dispatcher.handle_payload(bytes.fromhex("0000"))

        self.assertEqual(output.events, [("press", "KEY_UP"), ("release", "KEY_UP")])

    def test_switching_actions_releases_previous_key(self) -> None:
        output = FakeOutput()
        dispatcher = ActionDispatcher(mapping=MappingConfig.default(), output=output, stream=io.StringIO())

        dispatcher.handle_payload(bytes.fromhex("0002"))
        dispatcher.handle_payload(bytes.fromhex("0008"))

        self.assertEqual(
            output.events,
            [("press", "KEY_UP"), ("release", "KEY_UP"), ("press", "KEY_DOWN")],
        )

    def test_unmapped_action_is_ignored(self) -> None:
        output = FakeOutput()
        mapping = MappingConfig(name="minimal", actions_to_keys={NormalizedAction.NAV_UP: "KEY_UP"})
        dispatcher = ActionDispatcher(mapping=mapping, output=output, stream=io.StringIO())

        dispatcher.handle_payload(bytes.fromhex("2000"))

        self.assertEqual(output.events, [])

    def test_runtime_reconnect_defaults_are_enabled(self) -> None:
        config = RuntimeConfig(device="AA:BB:CC:DD:EE:FF")

        self.assertTrue(config.reconnect)
        self.assertEqual(config.reconnect_delay, 2.0)
        self.assertEqual(config.max_reconnect_delay, 30.0)

    def test_remaining_timeout_clamps_to_zero(self) -> None:
        self.assertIsNone(_remaining_timeout(None))
        self.assertEqual(_remaining_timeout(time.monotonic() - 1), 0.0)

    def test_print_output_creation_accepts_mapping(self) -> None:
        mapping = MappingConfig(name="custom", actions_to_keys={NormalizedAction.NAV_UP: "KEY_F21"})

        output = create_output("print", mapping)

        self.assertIsNotNone(output)


if __name__ == "__main__":
    unittest.main()
