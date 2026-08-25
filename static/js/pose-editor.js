"use strict";

import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { TransformControls } from "three/addons/controls/TransformControls.js";

const POSE_FORMAT = "atomic-dance-pose";
const POSE_VERSION = 1;
const MODEL_ID = "ybot";
const MODEL_DISPLAY_HEIGHT = 170;
const AXES = ["X", "Y", "Z"];
const LOCAL_AXES = ["x", "y", "z"];
const COLORS = {
    sceneBackground: 0xdfe4ed,
    hemisphereSky: 0xffffff,
    hemisphereGround: 0x596273,
    keyLight: 0xffffff,
    ground: 0xcbd2dd,
    marker: 0xf43f5e,
    selectedMarker: 0xf59e0b,
};
const CAMERA = {
    fieldOfView: 35,
    initialAspect: 1,
    initialNear: 0.1,
    initialFar: 2000,
    initialPosition: [110, 95, 240],
    initialTargetHeight: 95,
    targetHeightRatio: 0.5,
    fittedX: 0,
    fittedHeightRatio: 0.55,
    fittedDistanceRatio: 1.3,
    nearHeightDivisor: 1000,
    farHeightRatio: 10,
};
const RENDERER_MAX_PIXEL_RATIO = 2;
const TRANSFORM = {
    initialSize: 0.75,
    minSize: 0.55,
    maxSize: 1,
    referenceModelHeight: 170,
};
const LIGHTING = {
    hemisphereIntensity: 2.4,
    keyIntensity: 3.5,
    keyPosition: [120, 180, 100],
};
const GROUND = {
    radius: 95,
    segments: 64,
    roughness: 1,
    height: 0,
};
const MATERIAL = {
    roughness: 0.7,
    metalness: 0,
    colorIntensity: 0.65,
};
const MARKER = {
    radius: 1.8,
    widthSegments: 18,
    heightSegments: 12,
    renderOrder: 20,
    normalScale: 1,
    selectedScale: 1.45,
};
const HALF = 0.5;
const NDC_SCALE = 2;
const NDC_OFFSET = 1;
const HALF_TURN_DEGREES = 180;
const FULL_TURN_DEGREES = 360;
const DISPLAY_DECIMAL_PLACES = 0;
const JSON_INDENT_SPACES = 2;
const QUATERNION_COMPONENT_COUNT = 4;
const FIRST_ITEM_INDEX = 0;
const MIN_RENDER_HEIGHT = 1;
const JOINT_GROUPS = [
    ["体幹", [["m_avg_Pelvis", "腰"], ["m_avg_Spine1", "背中"], ["m_avg_Spine3", "胸"], ["m_avg_Neck", "首"], ["m_avg_Head", "頭"]]],
    ["腕", [["m_avg_L_Shoulder", "左肩"], ["m_avg_R_Shoulder", "右肩"], ["m_avg_L_Elbow", "左ひじ"], ["m_avg_R_Elbow", "右ひじ"], ["m_avg_L_Wrist", "左手首"], ["m_avg_R_Wrist", "右手首"]]],
    ["脚", [["m_avg_L_Hip", "左脚の付け根"], ["m_avg_R_Hip", "右脚の付け根"], ["m_avg_L_Knee", "左ひざ"], ["m_avg_R_Knee", "右ひざ"], ["m_avg_L_Ankle", "左足首"], ["m_avg_R_Ankle", "右足首"]]],
];
const EDITABLE_JOINTS = new Map(JOINT_GROUPS.flatMap(([, joints]) => joints));

const viewport = document.getElementById("viewport");
const scene = new THREE.Scene();
scene.background = new THREE.Color(COLORS.sceneBackground);
const camera = new THREE.PerspectiveCamera(
    CAMERA.fieldOfView,
    CAMERA.initialAspect,
    CAMERA.initialNear,
    CAMERA.initialFar,
);
camera.position.set(...CAMERA.initialPosition);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, RENDERER_MAX_PIXEL_RATIO));
renderer.shadowMap.enabled = true;
renderer.outputColorSpace = THREE.SRGBColorSpace;
viewport.appendChild(renderer.domElement);

const orbit = new OrbitControls(camera, renderer.domElement);
orbit.enableDamping = true;
orbit.target.set(CAMERA.fittedX, CAMERA.initialTargetHeight, CAMERA.fittedX);

const transform = new TransformControls(camera, renderer.domElement);
transform.setMode("rotate");
transform.setSpace("local");
transform.setSize(TRANSFORM.initialSize);
scene.add(transform.getHelper());
transform.addEventListener("dragging-changed", (event) => { orbit.enabled = !event.value; });
transform.addEventListener("objectChange", () => {
    updateSkeletons();
    syncRotationControls();
});

scene.add(new THREE.HemisphereLight(
    COLORS.hemisphereSky,
    COLORS.hemisphereGround,
    LIGHTING.hemisphereIntensity,
));
const keyLight = new THREE.DirectionalLight(COLORS.keyLight, LIGHTING.keyIntensity);
keyLight.position.set(...LIGHTING.keyPosition);
keyLight.castShadow = true;
scene.add(keyLight);

const ground = new THREE.Mesh(
    new THREE.CircleGeometry(GROUND.radius, GROUND.segments),
    new THREE.MeshStandardMaterial({ color: COLORS.ground, roughness: GROUND.roughness }),
);
ground.rotation.x = -Math.PI * HALF;
ground.receiveShadow = true;
scene.add(ground);

let model;
let selectedBone;
const bones = new Map();
const skeletons = new Set();
const initialRotations = new Map();
const markers = [];
const tunedMaterials = new WeakSet();
const markerGeometry = new THREE.SphereGeometry(
    MARKER.radius,
    MARKER.widthSegments,
    MARKER.heightSegments,
);
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

buildJointButtons();
bindInterface();
loadModel();
resizeRenderer();
renderer.setAnimationLoop(render);

async function loadModel() {
    try {
        const gltf = await new GLTFLoader().loadAsync(document.body.dataset.modelUrl);
        model = gltf.scene;
        model.traverse((object) => {
            if (object.isMesh) {
                object.castShadow = true;
                object.receiveShadow = true;
                if (Array.isArray(object.material)) object.material.forEach(tuneMaterial);
                else tuneMaterial(object.material);
            }
            if (object.isSkinnedMesh && object.skeleton) {
                skeletons.add(object.skeleton);
                object.skeleton.bones.forEach((bone) => bones.set(bone.name, bone));
            }
        });
        // スキンに含まれない補助ボーンだけを補完する。同名の場合は、実際に
        // メッシュ変形へ使われるSkeleton側のボーンを必ず優先する。
        model.traverse((object) => {
            if (object.isBone && !bones.has(object.name)) bones.set(object.name, object);
        });
        if (!bones.size) throw new Error("モデル内にボーンが見つかりません。");

        fitModelToViewport();
        createJointMarkers();
        EDITABLE_JOINTS.forEach((label, name) => {
            const bone = bones.get(name);
            if (bone) initialRotations.set(name, bone.quaternion.clone());
        });
        scene.add(model);
        document.getElementById("loadingStatus").hidden = true;
        const firstAvailable = [...EDITABLE_JOINTS.keys()].find((name) => bones.has(name));
        if (firstAvailable) selectJoint(firstAvailable);
        setMessage(`${bones.size}個のボーンを読み込みました。`);
    } catch (error) {
        const status = document.getElementById("loadingStatus");
        status.textContent = `YBotを読み込めませんでした: ${error.message}`;
        setMessage(error.message, true);
    }
}

function tuneMaterial(material) {
    if (!material || tunedMaterials.has(material)) return;
    tunedMaterials.add(material);
    material.roughness = MATERIAL.roughness;
    material.metalness = MATERIAL.metalness;
    if (material.color) material.color.multiplyScalar(MATERIAL.colorIntensity);
}

function fitModelToViewport() {
    let bounds = new THREE.Box3().setFromObject(model);
    const sourceSize = bounds.getSize(new THREE.Vector3());
    const scale = MODEL_DISPLAY_HEIGHT / sourceSize.y;
    model.scale.multiplyScalar(scale);
    model.updateMatrixWorld(true);

    bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    model.position.sub(center);
    model.position.y += size.y * HALF;
    ground.position.y = GROUND.height;
    orbit.target.set(CAMERA.fittedX, size.y * CAMERA.targetHeightRatio, CAMERA.fittedX);
    const distance = size.y / (
        NDC_SCALE * Math.tan(THREE.MathUtils.degToRad(camera.fov * HALF))
    );
    camera.position.set(
        CAMERA.fittedX,
        size.y * CAMERA.fittedHeightRatio,
        distance * CAMERA.fittedDistanceRatio,
    );
    camera.near = Math.max(CAMERA.initialNear, size.y / CAMERA.nearHeightDivisor);
    camera.far = size.y * CAMERA.farHeightRatio;
    camera.updateProjectionMatrix();
    transform.setSize(Math.max(
        TRANSFORM.minSize,
        Math.min(TRANSFORM.maxSize, TRANSFORM.referenceModelHeight / size.y),
    ));
}

function createJointMarkers() {
    EDITABLE_JOINTS.forEach((label, name) => {
        const bone = bones.get(name);
        if (!bone) return;
        const material = new THREE.MeshBasicMaterial({ color: COLORS.marker, depthTest: false });
        const marker = new THREE.Mesh(markerGeometry, material);
        marker.renderOrder = MARKER.renderOrder;
        marker.userData.boneName = name;
        marker.userData.bone = bone;
        markers.push(marker);
        scene.add(marker);
    });
}

function buildJointButtons() {
    const container = document.getElementById("jointGroups");
    JOINT_GROUPS.forEach(([groupName, joints]) => {
        const group = document.createElement("div");
        group.className = "joint-group";
        const heading = document.createElement("h4");
        heading.textContent = groupName;
        const buttons = document.createElement("div");
        buttons.className = "joint-buttons";
        joints.forEach(([name, label]) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "joint-button";
            button.dataset.joint = name;
            button.textContent = label;
            button.addEventListener("click", () => selectJoint(name));
            buttons.appendChild(button);
        });
        group.append(heading, buttons);
        container.appendChild(group);
    });
}

function bindInterface() {
    window.addEventListener("resize", resizeRenderer);
    renderer.domElement.addEventListener("pointerdown", selectMarkerAtPointer);
    AXES.forEach((axis) => {
        document.getElementById(`rotation${axis}`).addEventListener("input", applySliderRotation);
    });
    document.getElementById("resetJoint").addEventListener("click", resetSelectedJoint);
    document.getElementById("resetPose").addEventListener("click", resetPose);
    document.getElementById("savePose").addEventListener("click", savePose);
    document.getElementById("loadPose").addEventListener("click", () => document.getElementById("poseFile").click());
    document.getElementById("poseFile").addEventListener("change", loadPose);
}

function selectMarkerAtPointer(event) {
    if (transform.dragging || !markers.length) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * NDC_SCALE - NDC_OFFSET;
    pointer.y = -((event.clientY - rect.top) / rect.height) * NDC_SCALE + NDC_OFFSET;
    raycaster.setFromCamera(pointer, camera);
    const hit = raycaster.intersectObjects(markers, false)[FIRST_ITEM_INDEX];
    if (hit) selectJoint(hit.object.userData.boneName);
}

function selectJoint(name) {
    const bone = bones.get(name);
    if (!bone) {
        setMessage(`${EDITABLE_JOINTS.get(name) || name}はモデル内に見つかりません。`, true);
        return;
    }
    selectedBone = bone;
    transform.attach(bone);
    document.getElementById("selectedJointName").textContent = EDITABLE_JOINTS.get(name) || name;
    document.getElementById("selectedJointHint").textContent = name;
    document.getElementById("resetJoint").disabled = false;
    document.querySelectorAll(".joint-button").forEach((button) => {
        button.classList.toggle("selected", button.dataset.joint === name);
    });
    markers.forEach((marker) => {
        marker.material.color.setHex(
            marker.userData.boneName === name ? COLORS.selectedMarker : COLORS.marker,
        );
        marker.scale.setScalar(
            marker.userData.boneName === name ? MARKER.selectedScale : MARKER.normalScale,
        );
    });
    syncRotationControls();
}

function applySliderRotation() {
    if (!selectedBone) return;
    selectedBone.rotation.set(
        THREE.MathUtils.degToRad(Number(document.getElementById("rotationX").value)),
        THREE.MathUtils.degToRad(Number(document.getElementById("rotationY").value)),
        THREE.MathUtils.degToRad(Number(document.getElementById("rotationZ").value)),
        selectedBone.rotation.order,
    );
    updateSkeletons();
    syncRotationControls();
}

function syncRotationControls() {
    if (!selectedBone) return;
    LOCAL_AXES.forEach((axis) => {
        const input = document.getElementById(`rotation${axis.toUpperCase()}`);
        const degrees = normalizeDegrees(THREE.MathUtils.radToDeg(selectedBone.rotation[axis]));
        input.disabled = false;
        input.value = degrees.toFixed(DISPLAY_DECIMAL_PLACES);
        input.nextElementSibling.value = `${degrees.toFixed(DISPLAY_DECIMAL_PLACES)}°`;
    });
}

function normalizeDegrees(value) {
    return (
        (value + HALF_TURN_DEGREES) % FULL_TURN_DEGREES + FULL_TURN_DEGREES
    ) % FULL_TURN_DEGREES - HALF_TURN_DEGREES;
}

function resetSelectedJoint() {
    const initial = selectedBone && initialRotations.get(selectedBone.name);
    if (!initial) return;
    selectedBone.quaternion.copy(initial);
    updateSkeletons();
    syncRotationControls();
    setMessage(`${EDITABLE_JOINTS.get(selectedBone.name)}を初期角度に戻しました。`);
}

function resetPose() {
    if (!model) return;
    initialRotations.forEach((quaternion, name) => bones.get(name)?.quaternion.copy(quaternion));
    updateSkeletons();
    syncRotationControls();
    setMessage("すべての関節を初期姿勢に戻しました。");
}

function serializePose() {
    const joints = {};
    EDITABLE_JOINTS.forEach((label, name) => {
        const bone = bones.get(name);
        if (bone) joints[name] = bone.quaternion.toArray();
    });
    return { format: POSE_FORMAT, version: POSE_VERSION, model: MODEL_ID, savedAt: new Date().toISOString(), joints };
}

function savePose() {
    if (!model) return;
    const blob = new Blob(
        [JSON.stringify(serializePose(), null, JSON_INDENT_SPACES)],
        { type: "application/json" },
    );
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `ybot-pose-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
    setMessage("姿勢をJSONファイルに保存しました。");
}

async function loadPose(event) {
    const file = event.target.files[FIRST_ITEM_INDEX];
    event.target.value = "";
    if (!file || !model) return;
    try {
        const data = JSON.parse(await file.text());
        validatePose(data);
        Object.entries(data.joints).forEach(([name, values]) => {
            const bone = bones.get(name);
            if (bone) {
                bone.quaternion.fromArray(values).normalize();
            }
        });
        updateSkeletons();
        syncRotationControls();
        setMessage(`${file.name}から姿勢を復元しました。`);
    } catch (error) {
        setMessage(`JSONを読み込めませんでした: ${error.message}`, true);
    }
}

function validatePose(data) {
    if (data?.format !== POSE_FORMAT || data.version !== POSE_VERSION || data.model !== MODEL_ID) {
        throw new Error("対応していない姿勢ファイルです。");
    }
    if (!data.joints || typeof data.joints !== "object") throw new Error("関節データがありません。");
    Object.entries(data.joints).forEach(([name, values]) => {
        if (
            !EDITABLE_JOINTS.has(name)
            || !Array.isArray(values)
            || values.length !== QUATERNION_COMPONENT_COUNT
            || !values.every(Number.isFinite)
        ) {
            throw new Error(`関節データが不正です: ${name}`);
        }
    });
}

function resizeRenderer() {
    const width = viewport.clientWidth;
    const height = viewport.clientHeight;
    renderer.setSize(width, height, false);
    camera.aspect = width / Math.max(height, MIN_RENDER_HEIGHT);
    camera.updateProjectionMatrix();
}

function render() {
    orbit.update();
    updateSkeletons();
    markers.forEach((marker) => marker.userData.bone.getWorldPosition(marker.position));
    renderer.render(scene, camera);
}

function updateSkeletons() {
    if (!model) return;
    model.updateMatrixWorld(true);
    skeletons.forEach((skeleton) => skeleton.update());
}

function setMessage(message, isError = false) {
    const element = document.getElementById("editorMessage");
    element.textContent = message;
    element.classList.toggle("error", isError);
}
