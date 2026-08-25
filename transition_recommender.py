"""Scores and ranks transitions between precomputed movement features."""

import numpy as np

from const import JOINTS


def default_joint_weights():
    weights = np.ones(len(JOINTS), dtype=np.float32)
    for index, name in enumerate(JOINTS):
        if any(part in name for part in ("Pelvis", "Spine", "Hip", "Knee", "Ankle", "Foot")):
            weights[index] = 2.0
        elif any(part in name for part in ("Wrist", "Hand", "Head")):
            weights[index] = 0.75
    return weights


def transition_distance(previous, following, joint_weights=None):
    weights = default_joint_weights() if joint_weights is None else np.asarray(joint_weights)
    offsets = previous.joint_positions - following.joint_positions
    pose_distance = np.average(np.linalg.norm(offsets, axis=1), weights=weights)
    velocity_distance = np.linalg.norm(previous.root_velocity - following.root_velocity)
    contact_penalty = np.count_nonzero(previous.foot_contacts != following.foot_contacts)
    return float(pose_distance + 0.35 * velocity_distance + 0.18 * contact_penalty)


def build_recommendations(features, limit=10):
    distances = {}
    all_values = []
    for source, source_features in features.items():
        distances[source] = []
        for target, target_features in features.items():
            distance = transition_distance(source_features["end"], target_features["start"])
            distances[source].append((target, distance))
            all_values.append(distance)
    scale = max(float(np.median(all_values)), 1e-8)
    recommendations = {}
    for source, candidates in distances.items():
        ranked = sorted(candidates, key=lambda item: (item[1], item[0]))[:limit]
        recommendations[str(source)] = [
            {"label": target, "score": round(100 * np.exp(-distance / scale))}
            for target, distance in ranked
        ]
    return recommendations
