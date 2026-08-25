# -*- coding: utf-8 -*-

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from const import (
    APP_DEBUG,
    APP_HOST,
    APP_PORT,
    HTTP_BAD_REQUEST,
    HTTP_INTERNAL_SERVER_ERROR,
    MAX_MOVEMENT_LABEL,
    MIN_MOVEMENT_LABEL,
    PREVIEWS_DIR_NAME,
    PROJECT_ROOT,
)
from dance_generator import DanceGenerationError, DanceGenerator


BASE_DIR = PROJECT_ROOT
PREVIEWS_DIR = BASE_DIR / PREVIEWS_DIR_NAME

dance_generator = DanceGenerator(BASE_DIR)

app = Flask(__name__)


@app.get("/")
def index():
    """Movement Libraryの画面を返す。"""

    return render_template("index.html")


@app.get("/pose-editor")
def pose_editor():
    """Phase 1の独立したポーズ編集画面を返す。"""

    return render_template("pose_editor.html")


@app.get("/assets/<path:filename>")
def model_asset(filename):
    """ポーズ編集画面で使用するモデル資産を返す。"""

    mimetype = "model/gltf-binary" if filename.lower().endswith(".glb") else None
    return send_from_directory(BASE_DIR / "assets", filename, mimetype=mimetype)


@app.get("/previews/<path:filename>")
def preview_asset(filename):
    """自動生成されたMovementデータとGIFを返す。"""

    mimetype = "image/webp" if filename.lower().endswith(".webp") else None
    return send_from_directory(PREVIEWS_DIR, filename, mimetype=mimetype)


@app.get("/generated/<path:filename>")
def generated_model(filename):
    """生成済みGLBを返す。"""

    return send_from_directory(
        dance_generator.generated_dir,
        filename,
    )


@app.post("/api/generate")
def generate_dance():
    """ステップ列を受信し、生成結果をJSONで返す。"""

    try:
        data = request.get_json(silent=True) or {}
        steps = data.get("steps")

        validation_error = validate_steps(steps)

        if validation_error:
            return jsonify({
                "ok": False,
                "error": validation_error,
            }), HTTP_BAD_REQUEST

        result = dance_generator.generate(steps)

        model_url = url_for(
            "generated_model",
            filename=result.glb_path.name,
        )

        return jsonify({
            "ok": True,
            "steps": list(result.steps),
            "model_url": model_url,
        })

    except DanceGenerationError as error:
        return jsonify({
            "ok": False,
            "error": str(error),
        }), HTTP_INTERNAL_SERVER_ERROR

    except Exception as error:
        print()
        print("Unexpected error:", repr(error))

        return jsonify({
            "ok": False,
            "error": f"{type(error).__name__}: {error}",
        }), HTTP_INTERNAL_SERVER_ERROR


def validate_steps(steps):
    """APIで受け取ったステップ列を検証する。"""

    if not steps:
        return "ステップを1つ以上選択してください。"

    if not isinstance(steps, list):
        return "stepsは配列で指定してください。"

    if not all(
        isinstance(step, int)
        and MIN_MOVEMENT_LABEL <= step <= MAX_MOVEMENT_LABEL
        for step in steps
    ):
        return "Labelは1〜100の整数で指定してください。"

    return None


if __name__ == "__main__":
    print()
    print("==============================")
    print("AtomicDance Builder")
    print("==============================")
    print()
    print("BASE_DIR:", BASE_DIR)
    print("Blender:", dance_generator.blender_exe)
    print(
        "Blender exists:",
        bool(
            dance_generator.blender_exe
            and dance_generator.blender_exe.exists()
        ),
    )
    print("YBot:", dance_generator.ybot_path)
    print("YBot exists:", dance_generator.ybot_path.exists())
    print()

    app.run(
        host=APP_HOST,
        port=APP_PORT,
        debug=APP_DEBUG,
    )
