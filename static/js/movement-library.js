"use strict";

const FAVORITES_STORAGE_KEY = "favoriteMovements";
const LABEL_WIDTH = 3;
const favoriteMovements = loadFavorites();
const state = {
    query: "",
    sort: "ascending",
    page: 1,
    pageSize: 16,
    favoritesOnly: false,
    recommendationsOnly: false,
};
let onSelectMovement = () => {};
let activeRecommendations = [];
let recommendationScores = new Map();

export function initializeMovementLibrary({ onSelect }) {
    onSelectMovement = onSelect;
    initializeDialog();
    initializeFilters();
    initializePagination();
    renderLibrary();
}

export function setMovementRecommendations(recommendations) {
    activeRecommendations = Array.isArray(recommendations) ? recommendations : [];
    recommendationScores = new Map(
        activeRecommendations.map((item) => [Number(item.label), Number(item.score)]),
    );
    renderRecommendations();
    renderLibrary();
}

function initializeDialog() {
    const dialog = document.getElementById("movementLibraryDialog");
    document.getElementById("openMovementLibrary").addEventListener(
        "click", () => dialog.showModal(),
    );
    document.getElementById("closeMovementLibrary").addEventListener(
        "click", () => dialog.close(),
    );
    dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close();
    });
}

function initializeFilters() {
    bindFilter("movementSearch", "input", (element) => {
        state.query = element.value.trim();
    });
    bindFilter("movementSort", "change", (element) => {
        state.sort = element.value;
    });
    bindFilter("movementPageSize", "change", (element) => {
        state.pageSize = Number(element.value);
    });
    bindFilter("favoritesOnly", "change", (element) => {
        state.favoritesOnly = element.checked;
    });
    bindFilter("recommendationsOnly", "change", (element) => {
        state.recommendationsOnly = element.checked;
    });
}

function bindFilter(elementId, eventName, updateState) {
    document.getElementById(elementId).addEventListener(eventName, (event) => {
        updateState(event.target);
        state.page = 1;
        renderLibrary();
    });
}

function initializePagination() {
    bindPageButtons(["previousMovementPage", "previousMovementPageBottom"], -1);
    bindPageButtons(["nextMovementPage", "nextMovementPageBottom"], 1);
}

function bindPageButtons(ids, direction) {
    for (const id of ids) {
        document.getElementById(id).addEventListener("click", () => changePage(direction));
    }
}

function changePage(direction) {
    state.page += direction;
    renderLibrary();
    document.getElementById("movementLibraryDialog").scrollTo({
        top: 0,
        behavior: "smooth",
    });
}

function renderLibrary() {
    const container = document.getElementById("movementLibrary");
    const movements = window.ATOMIC_MOVEMENTS ?? [];
    const filtered = filterAndSort(movements);
    const pageCount = Math.max(1, Math.ceil(filtered.length / state.pageSize));
    state.page = Math.min(Math.max(1, state.page), pageCount);
    const start = (state.page - 1) * state.pageSize;
    const visible = filtered.slice(start, start + state.pageSize);

    container.replaceChildren();
    updateStatus(filtered.length, movements.length, pageCount);
    if (visible.length === 0) {
        const message = document.createElement("p");
        message.className = "empty";
        message.textContent = "No movements match the current filters.";
        container.appendChild(message);
        return;
    }
    for (const movement of visible) container.appendChild(createCard(movement));
}

function filterAndSort(movements) {
    const query = state.query.toLowerCase().replace(/^label\s*/, "");
    return movements
        .filter((movement) => {
            const label = String(movement.label);
            const paddedLabel = formatLabel(movement.label);
            const matchesQuery = !query || label.includes(query) || paddedLabel.includes(query);
            const matchesFavorite = !state.favoritesOnly
                || favoriteMovements.has(movement.label);
            const matchesRecommendation = !state.recommendationsOnly
                || recommendationScores.has(movement.label);
            return matchesQuery && matchesFavorite && matchesRecommendation;
        })
        .sort((first, second) => {
            if (state.recommendationsOnly) {
                return recommendationScores.get(second.label)
                    - recommendationScores.get(first.label);
            }
            return state.sort === "ascending"
                ? first.label - second.label
                : second.label - first.label;
        });
}

function createCard(movement, score = recommendationScores.get(movement.label)) {
    const paddedLabel = formatLabel(movement.label);
    const card = document.createElement("article");
    const title = document.createElement("h3");
    const preview = document.createElement("img");
    const actions = document.createElement("div");
    const favoriteButton = document.createElement("button");
    const addButton = document.createElement("button");

    card.className = "card";
    title.textContent = `Label ${paddedLabel}`;
    preview.src = movement.previewUrl;
    preview.alt = `Label ${paddedLabel}`;
    preview.loading = "lazy";
    actions.className = "card-actions";
    favoriteButton.type = "button";
    favoriteButton.className = "favorite-button";
    favoriteButton.textContent = favoriteMovements.has(movement.label)
        ? "\u2605" : "\u2606";
    favoriteButton.title = "Toggle favorite";
    favoriteButton.setAttribute("aria-label", `Toggle favorite for Label ${paddedLabel}`);
    favoriteButton.addEventListener("click", () => toggleFavorite(movement.label));
    addButton.type = "button";
    addButton.textContent = "\uFF0B Add";
    addButton.addEventListener("click", () => onSelectMovement(movement.label));
    actions.append(favoriteButton, addButton);
    card.append(title);
    if (score !== undefined) {
        const compatibility = document.createElement("p");
        compatibility.className = "compatibility-score";
        compatibility.textContent = `つながりやすさ ${score}`;
        card.appendChild(compatibility);
    }
    card.append(preview, actions);
    return card;
}

function renderRecommendations() {
    const section = document.getElementById("movementRecommendationsSection");
    const container = document.getElementById("movementRecommendations");
    if (!section || !container) return;
    const movements = window.ATOMIC_MOVEMENTS ?? [];
    const byLabel = new Map(movements.map((movement) => [movement.label, movement]));
    container.replaceChildren();
    for (const recommendation of activeRecommendations) {
        const movement = byLabel.get(Number(recommendation.label));
        if (movement) container.appendChild(createCard(movement, recommendation.score));
    }
    section.hidden = container.children.length === 0;
}

function updateStatus(filteredCount, totalCount, pageCount) {
    document.getElementById("movementCount").textContent = (
        `${filteredCount} of ${totalCount} movements`
    );
    const pageText = `Page ${state.page} / ${pageCount}`;
    document.getElementById("movementPageStatus").textContent = pageText;
    document.getElementById("movementPageStatusBottom").textContent = pageText;
    setButtonsDisabled(
        ["previousMovementPage", "previousMovementPageBottom"],
        state.page <= 1,
    );
    setButtonsDisabled(
        ["nextMovementPage", "nextMovementPageBottom"],
        state.page >= pageCount,
    );
}

function setButtonsDisabled(ids, disabled) {
    for (const id of ids) document.getElementById(id).disabled = disabled;
}

function toggleFavorite(label) {
    if (favoriteMovements.has(label)) favoriteMovements.delete(label);
    else favoriteMovements.add(label);
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify([...favoriteMovements]));
    renderLibrary();
}

function loadFavorites() {
    try {
        const labels = JSON.parse(localStorage.getItem(FAVORITES_STORAGE_KEY) || "[]");
        return new Set(labels.map(Number));
    } catch (error) {
        console.warn("Could not load favorite movements.", error);
        return new Set();
    }
}

function formatLabel(label) {
    return String(label).padStart(LABEL_WIDTH, "0");
}
