"use strict";

import { setMovementRecommendations } from "./movement-library.js";

let recommendations = {};
let currentSteps = [];

export async function initializeMovementRecommendations() {
    try {
        const response = await fetch("/previews/movement-transitions.json");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        recommendations = payload.recommendations ?? {};
    } catch (error) {
        console.warn("Movement recommendations are unavailable.", error);
        recommendations = {};
    }
    update(currentSteps);
    document.addEventListener("dance-steps-changed", (event) => {
        update(event.detail.steps);
    });
}

export function updateMovementRecommendations(steps) {
    update(steps);
}

function update(steps) {
    currentSteps = [...steps];
    const finalLabel = steps.at(-1);
    setMovementRecommendations(finalLabel === undefined
        ? []
        : recommendations[String(finalLabel)] ?? []);
}
