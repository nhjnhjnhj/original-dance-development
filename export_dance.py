import json
import pickle

import numpy as np
import torch
from scipy.spatial.transform import Rotation, Slerp
import argparse

from const import (
    DANCE_FILENAME_PREFIX,
    DATA_ROOT,
    DATASET_SPLITS,
    EXPORTED_DIR_NAME,
    JOINT_COUNT,
    LABEL_FORMAT_WIDTH,
    LABELS_FILENAME,
    MOTION_FILENAME,
    MOTION_METADATA_DIMS,
    NAMES_FILENAME,
    NORMALIZATION_EPSILON_MULTIPLIER,
    NORMALIZED_MAX,
    NORMALIZED_MIN,
    NORMALIZED_RANGE,
    NORMALIZER_FILENAME,
    POSE_DIMS,
    ROTATION_6D_DIMS,
    ROTATION_VECTOR_DIMS,
    STEPS_OPTION,
    TRANSITION_FRAMES,
    TRANSLATION_DIMS,
)

# ========================================
# 設定
# ========================================

parser = argparse.ArgumentParser()

parser.add_argument(
    STEPS_OPTION,
    nargs="+",
    type=int,
    required=True,
)

args = parser.parse_args()

DANCE_STEPS = args.steps

OUTPUT_DIR = DATA_ROOT.parent.parent / EXPORTED_DIR_NAME


# ========================================
# Atomic Movementを探す
# ========================================

def find_longest_segment(label):
    best = None

    for split in DATASET_SPLITS:
        root = DATA_ROOT / split

        labels = np.load(
            root / LABELS_FILENAME,
            mmap_mode="r"
        )

        with open(
            root / NAMES_FILENAME,
            encoding="utf-8"
        ) as f:
            names = json.load(f)

        for sample_index, sequence in enumerate(labels):

            indices = np.where(sequence == label)[0]

            if len(indices) == 0:
                continue

            groups = np.split(
                indices,
                np.where(np.diff(indices) != 1)[0] + 1
            )

            for group in groups:

                if best is None or len(group) > best["length"]:
                    best = {
                        "split": split,
                        "sample": sample_index,
                        "start": int(group[0]),
                        "end": int(group[-1]) + 1,
                        "length": len(group),
                        "name": names[sample_index],
                    }

    if best is None:
        raise ValueError(
            f"Atomic Movement {label} が見つかりません"
        )

    return best


# ========================================
# 6D Rotation → Rotation Matrix
# ========================================

def rotation_6d_to_matrix(d6):
    a1 = d6[..., :ROTATION_VECTOR_DIMS]
    a2 = d6[..., ROTATION_VECTOR_DIMS:]

    b1 = a1 / np.linalg.norm(
        a1,
        axis=-1,
        keepdims=True
    )

    b2 = (
        a2
        - np.sum(
            b1 * a2,
            axis=-1,
            keepdims=True
        ) * b1
    )

    b2 /= np.linalg.norm(
        b2,
        axis=-1,
        keepdims=True
    )

    b3 = np.cross(b1, b2)

    return np.stack(
        (b1, b2, b3),
        axis=-2
    )


# ========================================
# データを元のスケールへ戻す
# ========================================

normalizer = torch.load(
    DATA_ROOT / NORMALIZER_FILENAME,
    map_location="cpu",
    weights_only=True
)

data_min = normalizer["data_min"].numpy()
data_max = normalizer["data_max"].numpy()

data_range = data_max - data_min

safe_range = np.where(
    data_range < NORMALIZATION_EPSILON_MULTIPLIER * np.finfo(np.float32).eps,
    1.0,
    data_range
)


# ========================================
# Atomic MovementをSMPL形式で取得
# ========================================

def load_atomic(label):

    segment = find_longest_segment(label)

    root = DATA_ROOT / segment["split"]

    motion_all = np.load(
        root / MOTION_FILENAME,
        mmap_mode="r"
    )

    motion = np.array(
        motion_all[
            segment["sample"],
            segment["start"]:segment["end"]
        ],
        dtype=np.float32
    )

    # 正規化を解除
    motion = (
        (np.clip(motion, NORMALIZED_MIN, NORMALIZED_MAX) - NORMALIZED_MIN)
        * safe_range / NORMALIZED_RANGE
        + data_min
    )

    # 最初の4次元は足の接地情報
    values = motion[:, MOTION_METADATA_DIMS:]

    # ルート位置
    translations = values[:, :TRANSLATION_DIMS].copy()

    # 24関節 × 6D Rotation
    rotation_6d = values[:, TRANSLATION_DIMS:].reshape(
        -1,
        JOINT_COUNT,
        ROTATION_6D_DIMS
    )

    matrices = rotation_6d_to_matrix(
        rotation_6d
    )

    # Axis-Angleへ変換
    poses = Rotation.from_matrix(
        matrices.reshape(-1, ROTATION_VECTOR_DIMS, ROTATION_VECTOR_DIMS)
    ).as_rotvec().reshape(-1, POSE_DIMS)

    return poses, translations, segment


# ========================================
# 2つの姿勢を滑らかにつなぐ
# ========================================

def interpolate_pose(
    pose_a,
    pose_b,
    alpha
):
    result = np.zeros(POSE_DIMS)

    for joint in range(JOINT_COUNT):

        start = joint * ROTATION_VECTOR_DIMS
        end = start + ROTATION_VECTOR_DIMS

        rotations = Rotation.from_rotvec(
            np.stack([
                pose_a[start:end],
                pose_b[start:end]
            ])
        )

        slerp = Slerp(
            [0.0, 1.0],
            rotations
        )

        result[start:end] = (
            slerp([alpha])
            .as_rotvec()[0]
        )

    return result


# ========================================
# ダンスを組み立てる
# ========================================

all_poses = []
all_translations = []

print()
print("=== Dance Steps ===")

for step_index, label in enumerate(DANCE_STEPS):

    poses, translations, segment = load_atomic(label)

    print(
        f"{step_index + 1}. "
        f"Label {label} "
        f"({len(poses)} frames)"
    )

    print(
        f"   {segment['name']}"
    )

    # 最初のステップ
    if step_index == 0:

        # 開始位置を原点にする
        translations -= translations[0]

        all_poses.extend(poses)
        all_translations.extend(translations)

        continue

    previous_pose = np.array(all_poses[-1])
    previous_position = np.array(
        all_translations[-1]
    )

    # 次のステップの開始位置を
    # 前ステップの終了位置に合わせる
    translations = (
        translations
        - translations[0]
        + previous_position
    )

    next_pose = poses[0]
    next_position = translations[0]

    # --------------------------
    # Transition生成
    # --------------------------

    for transition_index in range(
        1,
        TRANSITION_FRAMES + 1
    ):

        alpha = (
            transition_index
            / (TRANSITION_FRAMES + 1)
        )

        transition_pose = interpolate_pose(
            previous_pose,
            next_pose,
            alpha
        )

        transition_position = (
            previous_position * (1 - alpha)
            + next_position * alpha
        )

        all_poses.append(
            transition_pose
        )

        all_translations.append(
            transition_position
        )

    # --------------------------
    # 次のステップを追加
    # --------------------------

    all_poses.extend(poses)
    all_translations.extend(translations)


# ========================================
# numpyへ変換
# ========================================

all_poses = np.asarray(
    all_poses,
    dtype=np.float32
)

all_translations = np.asarray(
    all_translations,
    dtype=np.float32
)


# ========================================
# PKL保存
# ========================================

OUTPUT_DIR.mkdir(exist_ok=True)

step_name = "_".join(
    f"{label:0{LABEL_FORMAT_WIDTH}d}"
    for label in DANCE_STEPS
)

output_path = (
    OUTPUT_DIR
    / f"{DANCE_FILENAME_PREFIX}_{step_name}.pkl"
)

with open(output_path, "wb") as f:

    pickle.dump(
        {
            "smpl_poses": all_poses,
            "smpl_trans": all_translations,
            "steps": DANCE_STEPS,
        },
        f
    )


print()
print("=== Export Complete ===")
print("Steps:", DANCE_STEPS)
print("Total frames:", len(all_poses))
print("Output:", output_path)
