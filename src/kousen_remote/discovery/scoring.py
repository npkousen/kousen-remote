from __future__ import annotations

from dataclasses import dataclass

from kousen_remote.model import DeviceRecord
from kousen_remote.profiles import DeviceProfile, ProfileMatch


@dataclass(frozen=True)
class Candidate:
    device: DeviceRecord
    profile: DeviceProfile
    match: ProfileMatch


def rank_candidates(
    devices: list[DeviceRecord],
    profiles: list[DeviceProfile],
    *,
    include_low_score: bool = False,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for device in devices:
        for profile in profiles:
            match = profile.score(device)
            if include_low_score or match.plausible:
                candidates.append(Candidate(device=device, profile=profile, match=match))
    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.match.score,
            candidate.device.rssi if candidate.device.rssi is not None else -999,
            candidate.device.display_name,
        ),
        reverse=True,
    )
