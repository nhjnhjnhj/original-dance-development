"""Shared AtomicDance dataset loading and forward-kinematics utilities."""

import json
from dataclasses import dataclass

import numpy as np
import torch

from const import (
    DATA_ROOT,
    DATASET_SPLITS,
    JOINT_COUNT,
    JOINT_OFFSETS,
    JOINT_PARENTS,
    LABELS_FILENAME,
    MOTION_FILENAME,
    MOTION_METADATA_DIMS,
    NAMES_FILENAME,
    NORMALIZED_MAX,
    NORMALIZED_MIN,
    NORMALIZED_RANGE,
    NORMALIZER_FILENAME,
    PROJECT_ROOT,
    ROTATION_6D_DIMS,
    ROTATION_EPSILON,
    ROTATION_VECTOR_DIMS,
    TRANSLATION_DIMS,
)


@dataclass(frozen=True)
class MovementSegment:
    split: str
    sample: int
    start: int
    end: int
    length: int
    name: str

    def as_dict(self):
        return {
            "split": self.split,
            "sample": self.sample,
            "start": self.start,
            "end": self.end,
            "length": self.length,
            "name": self.name,
        }


def dataset_root():
    return DATA_ROOT if DATA_ROOT.is_absolute() else PROJECT_ROOT / DATA_ROOT


def rotation_6d_to_matrix(rotation_6d):
    rotation_6d = np.asarray(rotation_6d)
    first = rotation_6d[..., :ROTATION_VECTOR_DIMS]
    second = rotation_6d[..., ROTATION_VECTOR_DIMS:]
    first /= np.maximum(
        np.linalg.norm(first, axis=-1, keepdims=True), ROTATION_EPSILON
    )
    second -= np.sum(first * second, axis=-1, keepdims=True) * first
    second /= np.maximum(
        np.linalg.norm(second, axis=-1, keepdims=True), ROTATION_EPSILON
    )
    third = np.cross(first, second)
    return np.stack((first, second, third), axis=-2)


def forward_kinematics(rotations, root_positions):
    rotations = np.asarray(rotations)
    root_positions = np.asarray(root_positions)
    frames = rotations.shape[0]
    positions = np.zeros((frames, JOINT_COUNT, 3), dtype=np.float32)
    world_rotations = np.zeros((frames, JOINT_COUNT, 3, 3), dtype=np.float32)
    offsets = np.asarray(JOINT_OFFSETS, dtype=np.float32)
    positions[:, 0] = root_positions
    world_rotations[:, 0] = rotations[:, 0]
    for joint in range(1, JOINT_COUNT):
        parent = JOINT_PARENTS[joint]
        positions[:, joint] = (
            np.einsum("fij,j->fi", world_rotations[:, parent], offsets[joint])
            + positions[:, parent]
        )
        world_rotations[:, joint] = world_rotations[:, parent] @ rotations[:, joint]
    return positions, world_rotations


class MotionDataset:
    """Loads each split once and exposes the longest segment per movement label."""

    def __init__(self, root=None):
        self.root = root or dataset_root()
        self.datasets = {}
        self.segments = {}
        self._load_index()
        normalizer = torch.load(
            self.root / NORMALIZER_FILENAME,
            map_location="cpu",
            weights_only=True,
        )
        self.data_min = normalizer["data_min"].numpy()
        self.data_max = normalizer["data_max"].numpy()
        data_range = self.data_max - self.data_min
        self.safe_range = np.where(
            data_range < 10 * np.finfo(np.float32).eps, 1.0, data_range
        )

    def _load_index(self):
        for split in DATASET_SPLITS:
            split_root = self.root / split
            labels = np.load(split_root / LABELS_FILENAME, mmap_mode="r")
            motion = np.load(split_root / MOTION_FILENAME, mmap_mode="r")
            with open(split_root / NAMES_FILENAME, encoding="utf-8") as file:
                names = json.load(file)
            self.datasets[split] = {"labels": labels, "motion": motion}
            for sample_index, sequence in enumerate(labels):
                start = 0
                while start < len(sequence):
                    label = int(sequence[start])
                    end = start + 1
                    while end < len(sequence) and sequence[end] == label:
                        end += 1
                    length = end - start
                    if label and (
                        label not in self.segments
                        or length > self.segments[label].length
                    ):
                        self.segments[label] = MovementSegment(
                            split, sample_index, start, end, length, names[sample_index]
                        )
                    start = end

    def load_movement(self, label):
        segment = self.segments[label]
        normalized = np.array(
            self.datasets[segment.split]["motion"][
                segment.sample, segment.start:segment.end
            ],
            dtype=np.float32,
        )
        motion = (
            (np.clip(normalized, NORMALIZED_MIN, NORMALIZED_MAX) - NORMALIZED_MIN)
            * self.safe_range
            / NORMALIZED_RANGE
            + self.data_min
        )
        values = motion[:, MOTION_METADATA_DIMS:]
        roots = values[:, :TRANSLATION_DIMS].copy()
        rotation_6d = values[:, TRANSLATION_DIMS:].reshape(
            -1, JOINT_COUNT, ROTATION_6D_DIMS
        )
        rotations = rotation_6d_to_matrix(rotation_6d)
        positions, world_rotations = forward_kinematics(rotations, roots)
        return positions, world_rotations, roots, segment
