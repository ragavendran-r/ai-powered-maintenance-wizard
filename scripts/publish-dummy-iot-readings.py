#!/usr/bin/env python3
import argparse
import asyncio
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone

import nats


@dataclass(frozen=True)
class SensorProfile:
    equipment_id: str
    signal: str
    unit: str
    baseline: float
    threshold: float
    noise: float
    anomaly_multiplier: float


SENSOR_PROFILES = [
    SensorProfile("RM-DRIVE-01", "drive_end_vibration", "mm/s", 4.8, 7.1, 0.35, 1.35),
    SensorProfile("RM-DRIVE-01", "bearing_temperature", "C", 76.0, 92.0, 2.0, 1.18),
    SensorProfile("BF-BLOWER-02", "outlet_pressure_variance", "kPa", 11.0, 18.0, 1.2, 1.45),
    SensorProfile("CC-PUMP-03", "cooling_water_flow", "m3/h", 1010.0, 1100.0, 18.0, 1.16),
    SensorProfile("HYD-SYS-04", "hydraulic_oil_temperature", "C", 68.0, 82.0, 1.8, 1.2),
    SensorProfile("HYD-SYS-04", "pressure_pulsation", "bar", 16.0, 24.0, 1.4, 1.45),
    SensorProfile("OH-CRANE-05", "hoist_motor_current", "A", 78.0, 95.0, 2.5, 1.24),
    SensorProfile("OH-CRANE-05", "hoist_brake_temperature", "C", 72.0, 88.0, 1.8, 1.22),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish dummy steel-plant IoT sensor readings to NATS JetStream.")
    parser.add_argument("--nats-url", default="nats://127.0.0.1:4222")
    parser.add_argument("--subject", default="steelplant.iot.sensor_readings")
    parser.add_argument("--source", default="dummy-iot-simulator")
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--anomaly-every-seconds", type=float, default=120.0)
    parser.add_argument("--scenario", choices=["normal", "spike", "degradation", "mixed"], default="mixed")
    parser.add_argument("--assets", default="all", help="Comma-separated equipment IDs or 'all'.")
    parser.add_argument("--once", action="store_true", help="Publish one batch and exit.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    selected_profiles = select_profiles(args.assets)
    nc = await nats.connect(args.nats_url)
    js = nc.jetstream()
    sequence = 0
    last_anomaly_at = 0.0
    try:
        while True:
            now = datetime.now(timezone.utc)
            monotonic_now = asyncio.get_running_loop().time()
            anomaly_active = args.scenario != "normal" and (
                args.once or monotonic_now - last_anomaly_at >= args.anomaly_every_seconds
            )
            if anomaly_active:
                last_anomaly_at = monotonic_now
            for profile in selected_profiles:
                sequence += 1
                value = simulated_value(profile, args.scenario, anomaly_active, sequence)
                message = {
                    "message_id": f"{args.source}-{now.strftime('%Y%m%d%H%M%S')}-{sequence:08d}",
                    "schema_version": "1",
                    "source": args.source,
                    "type": "sensor_reading",
                    "timestamp": now.isoformat().replace("+00:00", "Z"),
                    "payload": {
                        "equipment_id": profile.equipment_id,
                        "signal": profile.signal,
                        "value": round(value, 2),
                        "unit": profile.unit,
                        "threshold": profile.threshold,
                    },
                }
                await js.publish(args.subject, json.dumps(message).encode("utf-8"))
            print(
                f"Published {len(selected_profiles)} reading(s) at {now.isoformat()} "
                f"{'with anomaly injection' if anomaly_active else 'normal'}",
                flush=True,
            )
            if args.once:
                break
            await asyncio.sleep(args.interval_seconds)
    finally:
        await nc.drain()


def select_profiles(assets: str) -> list[SensorProfile]:
    if assets == "all":
        return SENSOR_PROFILES
    selected = {asset.strip() for asset in assets.split(",") if asset.strip()}
    profiles = [profile for profile in SENSOR_PROFILES if profile.equipment_id in selected]
    if not profiles:
        raise SystemExit(f"No sensor profiles matched assets: {assets}")
    return profiles


def simulated_value(profile: SensorProfile, scenario: str, anomaly_active: bool, sequence: int) -> float:
    wave = math.sin(sequence / 5) * profile.noise
    value = profile.baseline + wave + random.uniform(-profile.noise, profile.noise)
    if not anomaly_active:
        return value
    if scenario == "degradation":
        return max(value, profile.threshold * (1.02 + min(sequence % 12, 8) * 0.025))
    if scenario == "spike":
        return max(value, profile.threshold * profile.anomaly_multiplier)
    if scenario == "mixed":
        if sequence % 2 == 0:
            return max(value, profile.threshold * profile.anomaly_multiplier)
        return max(value, profile.threshold * 1.08)
    return value


if __name__ == "__main__":
    asyncio.run(main())
