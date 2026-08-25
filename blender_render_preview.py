"""Blender上でYBotのダンスを事前レンダリングしてWebMへ出力する。"""

import math
import pickle
import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from const import (  # noqa: E402
    ARGUMENT_SEPARATOR,
    ARMATURE_TYPE,
    BLENDER_ROTATION_MODE,
    JOINTS,
    MODEL_PREVIEW_BACKGROUND,
    MODEL_PREVIEW_CAMERA_AZIMUTH_DEGREES,
    MODEL_PREVIEW_CAMERA_DISTANCE,
    MODEL_PREVIEW_CENTER_X_OFFSET,
    MODEL_PREVIEW_ENGINE,
    MODEL_PREVIEW_FPS,
    MODEL_PREVIEW_FRAME_STEP,
    MODEL_PREVIEW_HEIGHT,
    MODEL_PREVIEW_IMAGE_FORMAT,
    MODEL_PREVIEW_MIN_ORTHO_SCALE,
    MODEL_PREVIEW_MATERIAL_COLOR,
    MODEL_PREVIEW_MATERIAL_ROUGHNESS,
    MODEL_PREVIEW_PADDING,
    MODEL_PREVIEW_WIDTH,
    PELVIS_JOINT,
    ROOT_CORRECTION_DEGREES,
    ROTATION_EPSILON,
    ROTATION_VECTOR_DIMS,
)


def parse_arguments():
    arguments = sys.argv[sys.argv.index(ARGUMENT_SEPARATOR) + 1:]
    if len(arguments) != 3:
        raise ValueError("Expected: <dance.pkl> <ybot.fbx> <frame-directory>")
    return tuple(Path(value).resolve() for value in arguments)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def import_ybot(fbx_path):
    bpy.ops.import_scene.fbx(filepath=str(fbx_path))
    for obj in bpy.data.objects:
        if obj.type == ARMATURE_TYPE and PELVIS_JOINT in obj.pose.bones:
            return obj
    raise RuntimeError("YBot armature was not found")


def apply_preview_material():
    material = bpy.data.materials.new("YBot Preview Blue")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = MODEL_PREVIEW_MATERIAL_COLOR
        principled.inputs["Roughness"].default_value = MODEL_PREVIEW_MATERIAL_ROUGHNESS

    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        obj.data.materials.clear()
        obj.data.materials.append(material)


def load_motion(pkl_path):
    with open(pkl_path, "rb") as file:
        data = pickle.load(file)
    return data["smpl_poses"], data["smpl_trans"]


def apply_animation(armature, poses, translations):
    root_correction = Quaternion(
        (1.0, 0.0, 0.0),
        math.radians(ROOT_CORRECTION_DEGREES),
    )
    sampled_indices = range(0, len(poses), MODEL_PREVIEW_FRAME_STEP)
    corrected_positions = []

    for output_index, source_index in enumerate(sampled_indices, start=1):
        frame = output_index
        for joint_index, joint_name in enumerate(JOINTS):
            bone = armature.pose.bones.get(joint_name)
            if bone is None:
                continue
            start = joint_index * ROTATION_VECTOR_DIMS
            rx, ry, rz = poses[source_index, start:start + ROTATION_VECTOR_DIMS]
            angle = math.sqrt(rx * rx + ry * ry + rz * rz)
            if angle > ROTATION_EPSILON:
                rotation = Quaternion(Vector((rx, ry, rz)) / angle, angle)
            else:
                rotation = Quaternion()
            if joint_name == PELVIS_JOINT:
                rotation = root_correction @ rotation
            bone.rotation_mode = BLENDER_ROTATION_MODE
            bone.rotation_quaternion = rotation
            bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)

        position = root_correction @ Vector(translations[source_index])
        corrected_positions.append(position.copy())
        pelvis = armature.pose.bones[PELVIS_JOINT]
        pelvis.location = position
        pelvis.keyframe_insert(data_path="location", frame=frame)

    return corrected_positions


def add_camera(positions):
    scene = bpy.context.scene
    scene.frame_set(1)
    bpy.context.view_layer.update()
    mesh_points = [
        obj.matrix_world @ Vector(corner)
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and not obj.hide_render
        for corner in obj.bound_box
    ]
    if not mesh_points:
        raise RuntimeError("YBot renderable meshes were not found")

    base_min_x = min(point.x for point in mesh_points)
    base_max_x = max(point.x for point in mesh_points)
    base_min_y = min(point.y for point in mesh_points)
    base_max_y = max(point.y for point in mesh_points)
    base_min_z = min(point.z for point in mesh_points)
    base_max_z = max(point.z for point in mesh_points)
    origin = positions[0]
    min_delta_x = min(position.x - origin.x for position in positions)
    max_delta_x = max(position.x - origin.x for position in positions)
    min_delta_y = min(position.y - origin.y for position in positions)
    max_delta_y = max(position.y - origin.y for position in positions)
    min_x = base_min_x + min_delta_x
    max_x = base_max_x + max_delta_x
    min_y = base_min_y + min_delta_y
    max_y = base_max_y + max_delta_y
    center = Vector((
        (min_x + max_x) / 2 + MODEL_PREVIEW_CENTER_X_OFFSET,
        (min_y + max_y) / 2,
        (base_min_z + base_max_z) / 2,
    ))

    camera_data = bpy.data.cameras.new("Preview Camera")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = max(
        MODEL_PREVIEW_MIN_ORTHO_SCALE,
        max_x - min_x + MODEL_PREVIEW_PADDING,
        base_max_z - base_min_z + MODEL_PREVIEW_PADDING,
    )
    camera = bpy.data.objects.new("Preview Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    azimuth = math.radians(MODEL_PREVIEW_CAMERA_AZIMUTH_DEGREES)
    camera.location = Vector((
        center.x + math.sin(azimuth) * MODEL_PREVIEW_CAMERA_DISTANCE,
        center.y - math.cos(azimuth) * MODEL_PREVIEW_CAMERA_DISTANCE,
        center.z,
    ))
    camera.rotation_euler = (center - camera.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = camera


def add_lighting():
    world = bpy.context.scene.world
    world.color = MODEL_PREVIEW_BACKGROUND[:3]
    world.use_nodes = True
    background_node = world.node_tree.nodes.get("Background")
    if background_node is not None:
        background_node.inputs["Color"].default_value = MODEL_PREVIEW_BACKGROUND
        background_node.inputs["Strength"].default_value = 0.35

    key_data = bpy.data.lights.new("Key Light", type="AREA")
    key_data.energy = 700
    key_data.shape = "DISK"
    key_data.size = 5.0
    key = bpy.data.objects.new("Key Light", key_data)
    bpy.context.collection.objects.link(key)
    key.location = (4.0, -4.0, 6.0)
    key.rotation_euler = (Vector((0.0, 0.0, 1.0)) - key.location).to_track_quat("-Z", "Y").to_euler()

    fill_data = bpy.data.lights.new("Fill Light", type="AREA")
    fill_data.energy = 320
    fill_data.size = 4.0
    fill = bpy.data.objects.new("Fill Light", fill_data)
    bpy.context.collection.objects.link(fill)
    fill.location = (-4.0, -2.0, 3.0)
    fill.rotation_euler = (Vector((0.0, 0.0, 1.0)) - fill.location).to_track_quat("-Z", "Y").to_euler()


def configure_render(output_directory, frame_count):
    scene = bpy.context.scene
    scene.render.engine = MODEL_PREVIEW_ENGINE
    scene.render.resolution_x = MODEL_PREVIEW_WIDTH
    scene.render.resolution_y = MODEL_PREVIEW_HEIGHT
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.fps = MODEL_PREVIEW_FPS
    scene.frame_start = 1
    scene.frame_end = frame_count
    scene.render.image_settings.file_format = MODEL_PREVIEW_IMAGE_FORMAT
    output_directory.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(output_directory / "frame_")


def main():
    pkl_path, fbx_path, output_directory = parse_arguments()
    clear_scene()
    armature = import_ybot(fbx_path)
    apply_preview_material()
    poses, translations = load_motion(pkl_path)
    positions = apply_animation(armature, poses, translations)
    add_camera(positions)
    add_lighting()
    configure_render(output_directory, len(positions))
    bpy.ops.render.render(animation=True)
    print("Model preview frames complete:", output_directory)


if __name__ == "__main__":
    main()
