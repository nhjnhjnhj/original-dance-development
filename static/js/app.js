"use strict";

import { initializeCameraControls } from "./camera-controls.js";
import { initializeDanceBuilder } from "./dance-builder.js";
import { initializeMovementLibrary } from "./movement-library.js";
import {
    initializeMovementRecommendations,
    updateMovementRecommendations,
} from "./movement-recommendations.js";

function initialize() {
    const danceBuilder = initializeDanceBuilder({
        onStepsChange: updateMovementRecommendations,
    });
    initializeMovementLibrary({ onSelect: danceBuilder.addStep });
    initializeMovementRecommendations();
    initializeCameraControls();
}

document.addEventListener("DOMContentLoaded", initialize);
