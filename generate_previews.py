import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
import numpy as np
import torch

from const import (
    DATA_ROOT,
    DATASET_SPLITS,
    GIF_PREVIEWS_DIR_NAME,
    JOINT_COUNT,
    JOINT_OFFSETS,
    JOINT_PARENTS,
    LABELS_FILENAME,
    LABEL_FORMAT_WIDTH,
    MOTION_FILENAME,
    MOTION_METADATA_DIMS,
    MOVEMENT_DATA_JSON_INDENT,
    MOVEMENT_DATA_FILENAME,
    NAMES_FILENAME,
    NORMALIZED_MAX,
    NORMALIZED_MIN,
    NORMALIZED_RANGE,
    NORMALIZER_FILENAME,
    PREVIEW_AZIMUTH,
    PREVIEW_DPI,
    PREVIEW_ELEVATION,
    PREVIEW_FIGURE_SIZE,
    PREVIEW_FPS,
    PREVIEW_FRAME_STEP,
    PREVIEW_INTERVAL_MS,
    PREVIEW_LABELS,
    PREVIEW_MIN_VIEW_SIZE,
    PREVIEW_MIN_Z_LIMIT,
    PREVIEW_VIEW_PADDING,
    PREVIEW_Z_PADDING,
    PREVIEWS_DIR_NAME,
    ROTATION_6D_DIMS,
    ROTATION_EPSILON,
    ROTATION_VECTOR_DIMS,
    TRANSLATION_DIMS,
    WEBP_PREVIEWS_DIR_NAME,
)

OUTPUT_DIR = Path(PREVIEWS_DIR_NAME)

# 現在プレビューを生成するLabel。全件生成する場合はrange(1, 101)にする。
LABELS = PREVIEW_LABELS

PARENTS = np.asarray(JOINT_PARENTS)
OFFSETS = np.asarray(JOINT_OFFSETS)


def rotation_6d_to_matrix(d6):
    a1 = d6[..., :ROTATION_VECTOR_DIMS]
    a2 = d6[..., ROTATION_VECTOR_DIMS:]
    eps = ROTATION_EPSILON

    b1 = a1 / (
        np.linalg.norm(a1, axis=-1, keepdims=True) + eps
    )
    b2 = a2 - np.sum(
        b1 * a2,
        axis=-1,
        keepdims=True,
    ) * b1
    b2 = b2 / (
        np.linalg.norm(b2, axis=-1, keepdims=True) + eps
    )
    b3 = np.cross(b1, b2)

    return np.stack((b1, b2, b3), axis=-2)


def forward_kinematics(rotations, root_positions):
    frames = rotations.shape[0]
    positions = np.zeros((frames, JOINT_COUNT, ROTATION_VECTOR_DIMS))
    world_rotations = np.zeros(
        (frames, JOINT_COUNT, ROTATION_VECTOR_DIMS, ROTATION_VECTOR_DIMS)
    )

    positions[:, 0] = root_positions
    world_rotations[:, 0] = rotations[:, 0]

    for joint in range(1, JOINT_COUNT):
        parent = PARENTS[joint]
        positions[:, joint] = (
            np.einsum(
                "fij,j->fi",
                world_rotations[:, parent],
                OFFSETS[joint],
            )
            + positions[:, parent]
        )
        world_rotations[:, joint] = (
            world_rotations[:, parent] @ rotations[:, joint]
        )

    return positions


def build_segment_index():
    best = {}
    datasets = {}

    for split in DATASET_SPLITS:
        root = DATA_ROOT / split
        motion = np.load(root / MOTION_FILENAME, mmap_mode="r")
        labels = np.load(root / LABELS_FILENAME, mmap_mode="r")

        with open(root / NAMES_FILENAME, encoding="utf-8") as file:
            names = json.load(file)

        datasets[split] = {
            "motion": motion,
            "labels": labels,
            "names": names,
        }

        for sample_index, sequence in enumerate(labels):
            start = 0

            while start < len(sequence):
                label = int(sequence[start])
                end = start + 1

                while end < len(sequence) and sequence[end] == label:
                    end += 1

                length = end - start

                if label != 0 and (
                    label not in best
                    or length > best[label]["length"]
                ):
                    best[label] = {
                        "split": split,
                        "sample": sample_index,
                        "start": start,
                        "end": end,
                        "length": length,
                        "name": names[sample_index],
                    }

                start = end

    return datasets, best


def load_normalizer():
    normalizer = torch.load(
        DATA_ROOT / NORMALIZER_FILENAME,
        map_location="cpu",
        weights_only=True,
    )

    return (
        normalizer["data_min"].numpy(),
        normalizer["data_max"].numpy(),
    )


def load_positions(
    label,
    datasets,
    segments,
    data_min,
    data_max,
):
    segment = segments[label]
    motion = np.array(
        datasets[segment["split"]]["motion"][
            segment["sample"],
            segment["start"]:segment["end"],
        ],
        dtype=np.float32,
    )

    motion = (
        (np.clip(motion, NORMALIZED_MIN, NORMALIZED_MAX) - NORMALIZED_MIN)
        * (data_max - data_min)
        / NORMALIZED_RANGE
        + data_min
    )
    values = motion[:, MOTION_METADATA_DIMS:]
    root_positions = values[:, :TRANSLATION_DIMS]
    rotations_6d = values[:, TRANSLATION_DIMS:].reshape(
        -1, JOINT_COUNT, ROTATION_6D_DIMS
    )
    rotations = rotation_6d_to_matrix(rotations_6d)
    positions = forward_kinematics(rotations, root_positions)

    corrected = np.empty_like(positions)
    corrected[..., 0] = positions[..., 0]
    corrected[..., 1] = positions[..., 2]
    corrected[..., 2] = -positions[..., 1]
    corrected -= corrected[0, 0]
    corrected[..., 2] -= corrected[..., 2].min()

    return corrected


def save_preview(
    label,
    datasets,
    segments,
    data_min,
    data_max,
):
    positions = load_positions(
        label,
        datasets,
        segments,
        data_min,
        data_max,
    )[::PREVIEW_FRAME_STEP]

    fig = plt.figure(figsize=PREVIEW_FIGURE_SIZE)
    ax = fig.add_subplot(111, projection="3d")
    lines = []

    for joint in range(1, JOINT_COUNT):
        line, = ax.plot([], [], [])
        lines.append((joint, line))

    xyz_min = positions.min(axis=(0, 1))
    xyz_max = positions.max(axis=(0, 1))
    center = (xyz_min + xyz_max) / 2
    size = max(
        max(xyz_max - xyz_min) * PREVIEW_VIEW_PADDING,
        PREVIEW_MIN_VIEW_SIZE,
    )

    ax.set_xlim(center[0] - size, center[0] + size)
    ax.set_ylim(center[1] - size, center[1] + size)
    ax.set_zlim(0, max(xyz_max[2] + PREVIEW_Z_PADDING, PREVIEW_MIN_Z_LIMIT))
    ax.set_title(f"Atomic Movement {label}")
    ax.set_axis_off()
    ax.view_init(elev=PREVIEW_ELEVATION, azim=PREVIEW_AZIMUTH)

    def update(frame):
        pose = positions[frame]

        for joint, line in lines:
            parent = PARENTS[joint]
            line.set_data(
                [pose[parent, 0], pose[joint, 0]],
                [pose[parent, 1], pose[joint, 1]],
            )
            line.set_3d_properties(
                [pose[parent, 2], pose[joint, 2]]
            )

        return [line for _, line in lines]

    animation = FuncAnimation(
        fig,
        update,
        frames=len(positions),
        interval=PREVIEW_INTERVAL_MS,
    )
    output = OUTPUT_DIR / GIF_PREVIEWS_DIR_NAME / f"label_{label:0{LABEL_FORMAT_WIDTH}d}.gif"

    try:
        animation.save(
            output,
            writer=PillowWriter(fps=PREVIEW_FPS),
            dpi=PREVIEW_DPI,
        )
    finally:
        plt.close(fig)

    print(f"Label {label:0{LABEL_FORMAT_WIDTH}d} -> {output}")


def write_movement_data(labels, segments):
    movements = [
        {
            "label": label,
            "previewUrl": get_preview_url(label),
        }
        for label in labels
        if label in segments
    ]
    javascript = (
        '"use strict";\n\n'
        "window.ATOMIC_MOVEMENTS = Object.freeze(\n"
        + json.dumps(
            movements,
            ensure_ascii=False,
            indent=MOVEMENT_DATA_JSON_INDENT,
        )
        + "\n);\n"
    )
    output = OUTPUT_DIR / MOVEMENT_DATA_FILENAME
    output.write_text(javascript, encoding="utf-8")

    return output


def get_preview_url(label):
    formatted_label = f"{label:0{LABEL_FORMAT_WIDTH}d}"
    model_preview = OUTPUT_DIR / WEBP_PREVIEWS_DIR_NAME / f"model_label_{formatted_label}.webp"
    if model_preview.exists():
        return f"/previews/{WEBP_PREVIEWS_DIR_NAME}/{model_preview.name}"
    return f"/previews/{GIF_PREVIEWS_DIR_NAME}/label_{formatted_label}.gif"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / GIF_PREVIEWS_DIR_NAME).mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / WEBP_PREVIEWS_DIR_NAME).mkdir(parents=True, exist_ok=True)
    data_min, data_max = load_normalizer()
    datasets, segments = build_segment_index()

    for label in LABELS:
        if label not in segments:
            print(f"Label {label:03d}: データなし")
            continue

        save_preview(
            label,
            datasets,
            segments,
            data_min,
            data_max,
        )

    movement_data_path = write_movement_data(LABELS, segments)

    print()
    print("==============================")
    print("Preview generation complete")
    print("==============================")
    print()
    print(f"JavaScript: {movement_data_path}")
    print()
    print("Webアプリから確認する場合:")
    print("uv run python app.py")


if __name__ == "__main__":
    main()
