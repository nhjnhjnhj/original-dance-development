"""Generate offline movement transition metadata and browser recommendations."""

import argparse
from datetime import datetime, timezone
import json

from const import PROJECT_ROOT
from motion_data import MotionDataset
from motion_features import extract_movement_features
from transition_recommender import build_recommendations

METADATA_PATH = PROJECT_ROOT / "data" / "movement-metadata.json"
TRANSITIONS_PATH = PROJECT_ROOT / "previews" / "movement-transitions.json"


def generate(limit=10, window_frames=5):
    dataset = MotionDataset()
    features = {}
    metadata = {}
    for label in sorted(dataset.segments):
        positions, _, roots, segment = dataset.load_movement(label)
        movement_features = extract_movement_features(positions, roots, window_frames)
        features[label] = movement_features
        metadata[str(label)] = {
            "source": segment.as_dict(),
            "start": movement_features["start"].as_dict(),
            "end": movement_features["end"].as_dict(),
        }
        print(f"Extracted Label {label:03d}")
    metadata_payload = {
        "schemaVersion": 1,
        "fps": 30,
        "windowFrames": window_frames,
        "movements": metadata,
    }
    transitions_payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "recommendations": build_recommendations(features, limit),
    }
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    TRANSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(json.dumps(metadata_payload, ensure_ascii=False), encoding="utf-8")
    TRANSITIONS_PATH.write_text(
        json.dumps(transitions_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return METADATA_PATH, TRANSITIONS_PATH


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--window-frames", type=int, default=5)
    arguments = parser.parse_args()
    paths = generate(arguments.limit, arguments.window_frames)
    print("Generated:", *paths, sep="\n")
