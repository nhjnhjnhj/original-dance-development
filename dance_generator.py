"""PKL生成からGLB生成までのダンス生成処理を提供する。"""

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence

from const import (
    ARGUMENT_SEPARATOR,
    BLENDER_BACKGROUND_OPTION,
    BLENDER_ENV_VAR,
    BLENDER_EXECUTABLE_PATTERN,
    BLENDER_EXPORT_SCRIPT_NAME,
    BLENDER_INSTALL_ROOT,
    BLENDER_PYTHON_OPTION,
    DANCE_FILENAME_PREFIX,
    EXPORTED_DIR_NAME,
    EXPORT_DANCE_SCRIPT_NAME,
    GENERATED_DIR_PARTS,
    KEEP_EXPORTED_PKL,
    LABEL_FORMAT_WIDTH,
    STEPS_OPTION,
    YBOT_PATH_PARTS,
)


class DanceGenerationError(RuntimeError):
    """ダンス生成に失敗したときに利用者向けメッセージを保持する。"""


@dataclass(frozen=True)
class DanceGenerationResult:
    """ダンス生成処理によって作成された成果物。"""

    steps: tuple[int, ...]
    pkl_path: Path
    glb_path: Path


def find_blender() -> Path | None:
    """環境変数または標準インストール先からBlenderを探す。"""

    env_path = os.environ.get(BLENDER_ENV_VAR)

    if env_path:
        path = Path(env_path)

        if path.exists():
            return path

    blender_root = BLENDER_INSTALL_ROOT

    if blender_root.exists():
        candidates = list(
            blender_root.glob(BLENDER_EXECUTABLE_PATTERN)
        )

        if candidates:
            candidates.sort(reverse=True)
            return candidates[0]

    return None


class DanceGenerator:
    """外部プロセスを実行し、ダンスのPKLとGLBを生成する。"""

    def __init__(
        self,
        base_dir: Path,
        blender_exe: Path | None = None,
    ) -> None:
        self.base_dir = base_dir.resolve()
        self.exported_dir = self.base_dir / EXPORTED_DIR_NAME
        self.generated_dir = self.base_dir.joinpath(*GENERATED_DIR_PARTS)
        self.ybot_path = self.base_dir.joinpath(*YBOT_PATH_PARTS)
        self.export_dance_script = self.base_dir / EXPORT_DANCE_SCRIPT_NAME
        self.blender_export_script = self.base_dir / BLENDER_EXPORT_SCRIPT_NAME
        self.blender_exe = blender_exe or find_blender()

    def generate(self, steps: Sequence[int]) -> DanceGenerationResult:
        """指定されたステップ列からPKLとGLBを生成する。"""

        selected_steps = tuple(steps)
        self._validate_required_files()

        self.exported_dir.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.generated_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        step_name = "_".join(
            f"{step:0{LABEL_FORMAT_WIDTH}d}"
            for step in selected_steps
        )
        pkl_path = self.exported_dir / f"{DANCE_FILENAME_PREFIX}_{step_name}.pkl"
        glb_path = self.generated_dir / f"{DANCE_FILENAME_PREFIX}_{step_name}.glb"

        self._export_pkl(selected_steps, pkl_path)
        self._export_glb(pkl_path, glb_path)

        if not KEEP_EXPORTED_PKL:
            pkl_path.unlink(missing_ok=True)

        return DanceGenerationResult(
            steps=selected_steps,
            pkl_path=pkl_path,
            glb_path=glb_path,
        )

    def _validate_required_files(self) -> None:
        if self.blender_exe is None:
            raise DanceGenerationError(
                "Blenderが見つかりません。インストール先を確認してください。"
            )

        if not self.blender_exe.exists():
            raise DanceGenerationError(
                f"Blenderが見つかりません: {self.blender_exe}"
            )

        if not self.ybot_path.exists():
            raise DanceGenerationError(
                f"ybot.fbxが見つかりません: {self.ybot_path}"
            )

        if not self.export_dance_script.exists():
            raise DanceGenerationError(
                f"export_dance.pyが見つかりません: {self.export_dance_script}"
            )

        if not self.blender_export_script.exists():
            raise DanceGenerationError(
                f"blender_export.pyが見つかりません: {self.blender_export_script}"
            )

    def _export_pkl(
        self,
        steps: tuple[int, ...],
        pkl_path: Path,
    ) -> None:
        pkl_path.unlink(missing_ok=True)

        command = [
            sys.executable,
            str(self.export_dance_script),
            STEPS_OPTION,
            *map(str, steps),
        ]

        print()
        print("=== Export Dance ===")
        print(command)

        result = subprocess.run(
            command,
            cwd=self.base_dir,
            capture_output=True,
            text=True,
            errors="replace",
        )

        if result.returncode != 0:
            print(result.stderr)
            raise DanceGenerationError(
                "PKLの生成に失敗しました。\n" + result.stderr
            )

        if not pkl_path.exists():
            raise DanceGenerationError(
                "PKL生成処理は終了しましたが、"
                f"ファイルが見つかりません: {pkl_path}"
            )

    def _export_glb(
        self,
        pkl_path: Path,
        glb_path: Path,
    ) -> None:
        glb_path.unlink(missing_ok=True)

        # _validate_required_files()の後にだけ呼び出されるため、
        # ここではblender_exeがPathであることが保証される。
        assert self.blender_exe is not None

        command = [
            str(self.blender_exe),
            BLENDER_BACKGROUND_OPTION,
            BLENDER_PYTHON_OPTION,
            str(self.blender_export_script),
            ARGUMENT_SEPARATOR,
            str(pkl_path),
            str(self.ybot_path),
            str(glb_path),
        ]

        print()
        print("=== Blender Export ===")
        print("Blender:", self.blender_exe)

        result = subprocess.run(
            command,
            cwd=self.base_dir,
            capture_output=True,
            text=True,
            errors="replace",
        )

        print(result.stdout)

        blender_output = result.stdout + result.stderr
        if "Traceback (most recent call last)" in blender_output:
            raise DanceGenerationError(
                "BlenderのPython処理に失敗しました。\n" + blender_output
            )

        if result.returncode != 0:
            print(result.stderr)
            raise DanceGenerationError(
                "GLBの生成に失敗しました。\n" + result.stderr
            )

        if not glb_path.exists():
            raise DanceGenerationError(
                "Blender処理は終了しましたが、"
                "GLBファイルが生成されていません。\n"
                f"{glb_path}"
            )
