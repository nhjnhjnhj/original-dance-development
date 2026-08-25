"use strict";

const LABEL_WIDTH = 3;
const selectedSteps = [];
let notifyStepsChange = () => {};

export function initializeDanceBuilder({ onStepsChange = () => {} } = {}) {
    notifyStepsChange = onStepsChange;
    renderSteps();
    document.getElementById("generateButton").addEventListener("click", generateDance);
    return { addStep, getSteps: () => [...selectedSteps] };
}

function notifyChange() {
    const steps = [...selectedSteps];
    notifyStepsChange(steps);
    document.dispatchEvent(new CustomEvent("dance-steps-changed", {
        detail: { steps },
    }));
}

function addStep(label) {
    selectedSteps.push(label);
    renderSteps();
    notifyChange();
}

function removeStep(index) {
    selectedSteps.splice(index, 1);
    renderSteps();
    notifyChange();
}

function moveStep(index, direction) {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= selectedSteps.length) return;
    [selectedSteps[index], selectedSteps[newIndex]] = [
        selectedSteps[newIndex], selectedSteps[index],
    ];
    renderSteps();
    notifyChange();
}

function renderSteps() {
    const container = document.getElementById("selectedSteps");
    container.replaceChildren();
    document.getElementById("openMovementLibrary").textContent = (
        `Open Movement Library (${selectedSteps.length} selected)`
    );
    if (selectedSteps.length === 0) {
        const message = document.createElement("p");
        message.className = "empty";
        message.textContent = "\u30b9\u30c6\u30c3\u30d7\u304c\u9078\u629e\u3055\u308c\u3066\u3044\u307e\u305b\u3093";
        container.appendChild(message);
        return;
    }

    selectedSteps.forEach((label, index) => {
        const step = document.createElement("div");
        const name = document.createElement("span");
        step.className = "step";
        name.className = "step-name";
        name.textContent = `${index + 1}. Label ${formatLabel(label)}`;
        step.append(
            name,
            createStepButton("\u2191", () => moveStep(index, -1)),
            createStepButton("\u2193", () => moveStep(index, 1)),
            createStepButton("\u00d7", () => removeStep(index)),
        );
        container.appendChild(step);
    });
}

function createStepButton(label, onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", onClick);
    return button;
}

function formatLabel(label) {
    return String(label).padStart(LABEL_WIDTH, "0");
}

async function generateDance() {
    if (selectedSteps.length === 0) {
        alert("Please select at least one step.");
        return;
    }
    const button = document.getElementById("generateButton");
    button.disabled = true;
    button.textContent = "Generating...";
    try {
        const response = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ steps: selectedSteps }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Dance generation failed.");
        const viewer = document.getElementById("danceViewer");
        viewer.src = `${result.model_url}?v=${Date.now()}`;
        viewer.style.display = "block";
    } catch (error) {
        console.error(error);
        alert(`Error:\n${error.message}`);
    } finally {
        button.disabled = false;
        button.textContent = "Generate Dance";
    }
}
