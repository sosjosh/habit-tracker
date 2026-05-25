console.log("Habit Quest Loaded");

// ── PROGRESS BARS ──
document.querySelectorAll(".progress-bar, .summary-bar, .todo-progress-bar").forEach(bar => {
    const progress = bar.dataset.progress;
    if (progress !== undefined) {
        bar.style.width = progress + "%";
    }
});

// ── AUTO-DISMISS FLASHES ──
setTimeout(() => {
    document.querySelectorAll(".flash").forEach(el => {
        el.style.transition = "opacity 0.5s ease";
        el.style.opacity = "0";
        setTimeout(() => el.remove(), 500);
    });
}, 4000);

// ── REDEEM CONFIRM ──
function confirmRedeem(name, cost, currentXp) {
    const remaining = currentXp - cost;
    return confirm(
        `Redeem "${name}" for ${cost} XP?\n` +
        `You have ${currentXp} XP — you'll have ${remaining} XP remaining.`
    );
}

// ── NOTE MODAL ──
function openNoteModal(habitId) {
    const modal = document.getElementById("note-modal");
    const form  = document.getElementById("note-form");
    form.action = `/complete/${habitId}`;
    modal.style.display = "flex";
    modal.querySelector("textarea").focus();
}

function closeNoteModal() {
    document.getElementById("note-modal").style.display = "none";
    document.getElementById("note-form").querySelector("textarea").value = "";
}

// Close modal on backdrop click
document.getElementById("note-modal").addEventListener("click", function(e) {
    if (e.target === this) closeNoteModal();
});

// ── DRAG TO REORDER ──
const habitList = document.getElementById("habit-list");
let draggedEl   = null;

if (habitList) {
    habitList.addEventListener("dragstart", e => {
        draggedEl = e.target.closest(".habit-card");
        if (draggedEl) draggedEl.classList.add("dragging");
    });

    habitList.addEventListener("dragend", e => {
        if (draggedEl) draggedEl.classList.remove("dragging");
        draggedEl = null;
        saveOrder();
    });

    habitList.addEventListener("dragover", e => {
        e.preventDefault();
        const target = e.target.closest(".habit-card");
        if (!target || target === draggedEl) return;

        const rect   = target.getBoundingClientRect();
        const midY   = rect.top + rect.height / 2;
        const before = e.clientY < midY;

        if (before) {
            habitList.insertBefore(draggedEl, target);
        } else {
            habitList.insertBefore(draggedEl, target.nextSibling);
        }
    });
}

function saveOrder() {
    const cards = document.querySelectorAll(".habit-card[data-id]");
    const ids   = Array.from(cards).map(c => c.dataset.id).join(",");

    fetch("/reorder", {
        method: "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body: `order=${ids}`
    });
}