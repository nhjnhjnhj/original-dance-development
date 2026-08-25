"""YBotを使ったMovement Library用アニメーションWebPを生成する。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import tempfile

from PIL import Image

from const import (
    ARGUMENT_SEPARATOR,
    BLENDER_BACKGROUND_OPTION,
    BLENDER_PYTHON_OPTION,
    DANCE_FILENAME_PREFIX,
    EXPORTED_DIR_NAME,
    EXPORT_DANCE_SCRIPT_NAME,
    LABEL_FORMAT_WIDTH,
    MODEL_PREVIEW_FRAME_DURATION_MS,
    MODEL_PREVIEW_BACKGROUND,
    MODEL_PREVIEW_WEBP_METHOD,
    MODEL_PREVIEW_WEBP_QUALITY,
    PREVIEWS_DIR_NAME,
    PROJECT_ROOT,
    STEPS_OPTION,
    YBOT_PATH_PARTS,
    WEBP_PREVIEWS_DIR_NAME,
)
from dance_generator import find_blender


BLENDER_PREVIEW_SCRIPT = PROJECT_ROOT / "blender_render_preview.py"
YBOT_PATH = PROJECT_ROOT.joinpath(*YBOT_PATH_PARTS)
EXPORTED_DIR = PROJECT_ROOT / EXPORTED_DIR_NAME
PREVIEWS_DIR = PROJECT_ROOT / PREVIEWS_DIR_NAME / WEBP_PREVIEWS_DIR_NAME


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", nargs="+", type=int, default=[1])
    parser.add_argument("--workers", type=int, default=1)
    return parser.parse_args()


def build_animated_webp(frame_directory, output_path):
    frame_paths = sorted(frame_directory.glob("frame_*.png"))
    if not frame_paths:
        raise RuntimeError("Blender did not render any preview frames")

    frames = []
    background_color = tuple(
        round(channel * 255)
        for channel in MODEL_PREVIEW_BACKGROUND[:3]
    )
    try:
        for frame_path in frame_paths:
            with Image.open(frame_path) as image:
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, (*background_color, 255))
                frames.append(Image.alpha_composite(background, rgba).convert("RGB"))
        first_frame, *remaining_frames = frames
        first_frame.save(
            output_path,
            format="WEBP",
            save_all=True,
            append_images=remaining_frames,
            duration=MODEL_PREVIEW_FRAME_DURATION_MS,
            loop=0,
            quality=MODEL_PREVIEW_WEBP_QUALITY,
            method=MODEL_PREVIEW_WEBP_METHOD,
        )
    finally:
        for frame in frames:
            frame.close()


def generate_preview(label, blender_exe):
    formatted_label = f"{label:0{LABEL_FORMAT_WIDTH}d}"
    pkl_path = EXPORTED_DIR / f"{DANCE_FILENAME_PREFIX}_{formatted_label}.pkl"
    output_path = PREVIEWS_DIR / f"model_label_{formatted_label}.webp"
    EXPORTED_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=f"model_label_{formatted_label}_",
        dir=PREVIEWS_DIR,
    ) as temporary_directory:
        frame_directory = Path(temporary_directory)
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / EXPORT_DANCE_SCRIPT_NAME),
                    STEPS_OPTION,
                    str(label),
                ],
                cwd=PROJECT_ROOT,
                check=True,
            )
            subprocess.run(
                [
                    str(blender_exe),
                    BLENDER_BACKGROUND_OPTION,
                    BLENDER_PYTHON_OPTION,
                    str(BLENDER_PREVIEW_SCRIPT),
                    ARGUMENT_SEPARATOR,
                    str(pkl_path),
                    str(YBOT_PATH),
                    str(frame_directory),
                ],
                cwd=PROJECT_ROOT,
                check=True,
            )
            build_animated_webp(frame_directory, output_path)
        finally:
            pkl_path.unlink(missing_ok=True)

    print(f"Label {formatted_label} -> {output_path}")
    return output_path


def main():
    arguments = parse_arguments()
    blender_exe = find_blender()
    if blender_exe is None:
        raise RuntimeError("Blender was not found")
    worker_count = max(1, arguments.workers)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        list(executor.map(
            lambda label: generate_preview(label, blender_exe),
            arguments.labels,
        ))


if __name__ == "__main__":
    main()
