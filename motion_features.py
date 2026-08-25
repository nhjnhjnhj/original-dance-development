"""Feature extraction for comparing Atomic Movement transitions."""

from dataclasses import dataclass

import numpy as np

from const import ANIMATION_FPS, JOINTS

LEFT_HIP = JOINTS.index("m_avg_L_Hip")
RIGHT_HIP = JOINTS.index("m_avg_R_Hip")
LEFT_ANKLE = JOINTS.index("m_avg_L_Ankle")
RIGHT_ANKLE = JOINTS.index("m_avg_R_Ankle")
LEFT_FOOT = JOINTS.index("m_avg_L_Foot")
RIGHT_FOOT = JOINTS.index("m_avg_R_Foot")
FOOT_JOINTS = ((LEFT_ANKLE, LEFT_FOOT), (RIGHT_ANKLE, RIGHT_FOOT))


@dataclass
class BoundaryFeature:
    joint_positions: np.ndarray
    root_velocity: np.ndarray
    foot_contacts: np.ndarray

    def as_dict(self):
        return {
            "jointPositions": np.round(self.joint_positions, 6).tolist(),
            "rootVelocity": np.round(self.root_velocity, 6).tolist(),
            "footContacts": self.foot_contacts.astype(bool).tolist(),
        }


def _facing_basis(positions):
    lateral = positions[RIGHT_HIP] - positions[LEFT_HIP]
    lateral[1] = 0
    norm = np.linalg.norm(lateral)
    if norm < 1e-8:
        lateral = np.array([1.0, 0.0, 0.0])
    else:
        lateral /= norm
    up = np.array([0.0, 1.0, 0.0])
    forward = np.cross(lateral, up)
    return np.stack((lateral, up, forward), axis=1)


def _boundary_feature(positions, roots, frame_slice):
    window = positions[frame_slice]
    root_window = roots[frame_slice]
    representative = np.mean(window, axis=0)
    basis = _facing_basis(representative)
    centered = representative - representative[0]
    normalized_positions = centered @ basis
    if len(root_window) > 1:
        velocity = np.mean(np.diff(root_window, axis=0), axis=0) * ANIMATION_FPS
    else:
        velocity = np.zeros(3)
    normalized_velocity = velocity @ basis
    frame_velocities = np.linalg.norm(np.diff(window, axis=0), axis=-1)
    if len(frame_velocities):
        joint_speeds = np.mean(frame_velocities, axis=0) * ANIMATION_FPS
    else:
        joint_speeds = np.zeros(window.shape[1])
    floor = np.min(positions[..., 1])
    contacts = []
    for ankle, foot in FOOT_JOINTS:
        height = min(representative[ankle, 1], representative[foot, 1]) - floor
        speed = min(joint_speeds[ankle], joint_speeds[foot])
        contacts.append(height < 0.12 and speed < 0.65)
    return BoundaryFeature(normalized_positions, normalized_velocity, np.array(contacts))


def extract_movement_features(positions, roots, window_frames=5):
    window = max(1, min(window_frames, len(positions)))
    return {
        "start": _boundary_feature(positions, roots, slice(0, window)),
        "end": _boundary_feature(positions, roots, slice(len(positions) - window, None)),
    }
