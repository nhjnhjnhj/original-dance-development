"use strict";

const CAMERA_LOG_DELAY_MS = 200;
const DEFAULT_CAMERA_ORBIT = "0deg 95deg 5.832m";
const DEFAULT_CAMERA_TARGET = "-3.043m 0.902m 0.022m";
const DEFAULT_FIELD_OF_VIEW = "30deg";
const HORIZONTAL_STEP = Math.PI / 12;
const VERTICAL_STEP = Math.PI / 18;
const MIN_VERTICAL_ANGLE = 0.1;
const ZOOM_IN_RATIO = 0.82;
const ZOOM_OUT_RATIO = 1.22;
let cameraLogTimer;

export function initializeCameraControls() {
    const viewer = getViewer();
    document.querySelectorAll("[data-camera-action]").forEach((button) => {
        button.addEventListener("click", () => updateCamera(button.dataset.cameraAction));
    });
    document.getElementById("animationToggle").addEventListener("click", toggleAnimation);
    viewer.addEventListener("load", () => {
        setAnimationButton(false);
        logCameraSettings("model loaded");
    });
    viewer.addEventListener("camera-change", () => {
        clearTimeout(cameraLogTimer);
        cameraLogTimer = setTimeout(
            () => logCameraSettings("camera changed"),
            CAMERA_LOG_DELAY_MS,
        );
    });
    window.showCameraSettings = () => logCameraSettings("manual");
}

function getViewer() {
    return document.getElementById("danceViewer");
}

function toggleAnimation() {
    const viewer = getViewer();
    if (!viewer.src) return;
    if (viewer.paused) {
        viewer.play();
        setAnimationButton(false);
    } else {
        viewer.pause();
        setAnimationButton(true);
    }
}

function setAnimationButton(isPaused) {
    const button = document.getElementById("animationToggle");
    button.innerHTML = isPaused ? "&#x25B6; Play" : "&#x23F8; Pause";
    button.setAttribute("aria-label", isPaused ? "Play animation" : "Pause animation");
}

function updateCamera(action) {
    const viewer = getViewer();
    if (action === "reset") {
        viewer.cameraOrbit = DEFAULT_CAMERA_ORBIT;
        viewer.cameraTarget = DEFAULT_CAMERA_TARGET;
        viewer.fieldOfView = DEFAULT_FIELD_OF_VIEW;
        viewer.jumpCameraToGoal();
        return;
    }

    let { theta, phi, radius } = viewer.getCameraOrbit();
    if (action === "left") theta -= HORIZONTAL_STEP;
    if (action === "right") theta += HORIZONTAL_STEP;
    if (action === "up") phi = Math.max(MIN_VERTICAL_ANGLE, phi - VERTICAL_STEP);
    if (action === "down") {
        phi = Math.min(Math.PI - MIN_VERTICAL_ANGLE, phi + VERTICAL_STEP);
    }
    if (action === "zoom-in") radius *= ZOOM_IN_RATIO;
    if (action === "zoom-out") radius *= ZOOM_OUT_RATIO;
    viewer.cameraOrbit = `${theta}rad ${phi}rad ${radius}m`;
    viewer.jumpCameraToGoal();
}

function logCameraSettings(reason) {
    const viewer = getViewer();
    if (!viewer.src) {
        console.info("3D Preview: generate a model before reading the camera.");
        return;
    }

    const orbit = viewer.getCameraOrbit();
    const target = viewer.getCameraTarget();
    const fieldOfView = viewer.getFieldOfView();
    const radiansToDegrees = 180 / Math.PI;
    const thetaDegrees = orbit.theta * radiansToDegrees;
    const phiDegrees = orbit.phi * radiansToDegrees;
    console.group(`3D Preview camera (${reason})`);
    console.table({
        theta: cameraValue(thetaDegrees, "deg", "horizontal rotation", 2),
        phi: cameraValue(phiDegrees, "deg", "vertical angle", 2),
        radius: cameraValue(orbit.radius, "m", "distance from target", 3),
        targetX: cameraValue(target.x, "m", "look-at X", 3),
        targetY: cameraValue(target.y, "m", "look-at Y", 3),
        targetZ: cameraValue(target.z, "m", "look-at Z", 3),
        fieldOfView: cameraValue(fieldOfView, "deg", "vertical field of view", 2),
    });
    console.log(`camera-orbit="${thetaDegrees.toFixed(2)}deg ${phiDegrees.toFixed(2)}deg ${orbit.radius.toFixed(3)}m"`);
    console.log(`camera-target="${target.x.toFixed(3)}m ${target.y.toFixed(3)}m ${target.z.toFixed(3)}m"`);
    console.log(`field-of-view="${fieldOfView.toFixed(2)}deg"`);
    console.groupEnd();
}

function cameraValue(value, unit, meaning, digits) {
    return { value: value.toFixed(digits), unit, meaning };
}
