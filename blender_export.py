import bpy
import pickle
import math
import sys
from pathlib import Path
from mathutils import Quaternion, Vector

# Blenderから実行した場合も、プロジェクト内のモジュールを読み込めるようにする。
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from const import (
    ANIMATION_FPS,
    ARGUMENT_SEPARATOR,
    ARMATURE_TYPE,
    BLENDER_ROTATION_MODE,
    FIRST_FRAME,
    GLTF_EXPORT_FORMAT,
    JOINTS,
    PELVIS_JOINT,
    ROOT_CORRECTION_DEGREES,
    ROTATION_EPSILON,
    ROTATION_VECTOR_DIMS,
)


# Blenderの "--" より後ろの引数を取得
args = sys.argv[sys.argv.index(ARGUMENT_SEPARATOR) + 1:]

pkl_path = Path(args[0]).resolve()
fbx_path = Path(args[1]).resolve()
output_path = Path(args[2]).resolve()

print("PKL:", pkl_path)
print("FBX:", fbx_path)
print("Output:", output_path)


# -------------------------
# シーンを空にする
# -------------------------

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)


# -------------------------
# YBot読み込み
# -------------------------

bpy.ops.import_scene.fbx(
    filepath=str(fbx_path)
)


# -------------------------
# Armatureを探す
# -------------------------

armature = None

for obj in bpy.data.objects:
    if obj.type == ARMATURE_TYPE:
        if PELVIS_JOINT in obj.pose.bones:
            armature = obj
            break

if armature is None:
    raise RuntimeError("YBot Armatureが見つかりません")


# -------------------------
# PKL読み込み
# -------------------------

with open(pkl_path, "rb") as f:
    data = pickle.load(f)

poses = data["smpl_poses"]
translations = data["smpl_trans"]

armature.animation_data_clear()


# -------------------------
# アニメーション設定
# -------------------------

scene = bpy.context.scene

scene.render.fps = ANIMATION_FPS
scene.frame_start = FIRST_FRAME
scene.frame_end = len(poses)


root_correction = Quaternion(
    (1.0, 0.0, 0.0),
    math.radians(ROOT_CORRECTION_DEGREES)
)


for frame_index in range(len(poses)):

    frame = frame_index + FIRST_FRAME

    for joint_index, joint_name in enumerate(JOINTS):

        bone = armature.pose.bones.get(joint_name)

        if bone is None:
            continue

        start = joint_index * ROTATION_VECTOR_DIMS

        rx, ry, rz = poses[
            frame_index,
            start:start + ROTATION_VECTOR_DIMS
        ]

        angle = math.sqrt(
            rx * rx +
            ry * ry +
            rz * rz
        )

        if angle > ROTATION_EPSILON:

            axis = Vector((
                rx / angle,
                ry / angle,
                rz / angle,
            ))

            rotation = Quaternion(
                axis,
                angle
            )

        else:
            rotation = Quaternion()

        if joint_name == PELVIS_JOINT:
            rotation = root_correction @ rotation

        bone.rotation_mode = BLENDER_ROTATION_MODE
        bone.rotation_quaternion = rotation

        bone.keyframe_insert(
            data_path="rotation_quaternion",
            frame=frame,
        )


    pelvis = armature.pose.bones[PELVIS_JOINT]

    position = Vector(
        translations[frame_index]
    )

    position = root_correction @ position

    pelvis.location = position

    pelvis.keyframe_insert(
        data_path="location",
        frame=frame,
    )


# -------------------------
# GLB出力
# -------------------------

output_path.parent.mkdir(
    parents=True,
    exist_ok=True
)

bpy.ops.export_scene.gltf(
    filepath=str(output_path),
    export_format=GLTF_EXPORT_FORMAT,
    export_animations=True,
)

print("GLB export complete:", output_path)
