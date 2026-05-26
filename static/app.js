console.log("Habit Quest Loaded");

// ── PROGRESS BARS ──
function updateBars() {
    document.querySelectorAll(
        ".progress-bar, .summary-bar, .todo-progress-bar"
    ).forEach(bar => {
        const progress = bar.dataset.progress;
        if (progress !== undefined) {
            bar.style.width = progress + "%";
        }
    });
}
updateBars();


// ── FLASH MESSAGES ──
function showFlash(category, text) {
    let container = document.querySelector(".flash-container");
    if (!container) {
        container = document.createElement("div");
        container.className = "flash-container";
        document.querySelector(".container").prepend(container);
    }

    const el = document.createElement("div");
    el.className = `flash flash-${category}`;
    el.innerHTML = text;
    container.appendChild(el);

    setTimeout(() => {
        el.style.transition = "opacity 0.5s ease";
        el.style.opacity    = "0";
        setTimeout(() => el.remove(), 500);
    }, 4000);
}

// Auto-dismiss any server-rendered flashes on load
setTimeout(() => {
    document.querySelectorAll(".flash").forEach(el => {
        el.style.transition = "opacity 0.5s ease";
        el.style.opacity    = "0";
        setTimeout(() => el.remove(), 500);
    });
}, 4000);


// ── AJAX HELPER ──
async function postForm(url, formData) {
    const resp = await fetch(url, {
        method:  "POST",
        headers: {"X-Requested-With": "XMLHttpRequest"},
        body:    formData,
    });
    return resp.json();
}


// ── DAILY SUMMARY UPDATE ──
function updateDailySummary(done, total) {
    const summaryText = document.querySelector(".summary-text");
    if (summaryText) {
        summaryText.innerHTML =
            `Today's Progress: <strong>${done} / ${total}</strong> habits done`;
    }

    const bar = document.querySelector(".summary-bar");
    if (bar) {
        const pct = total > 0 ? Math.round(done / total * 100) : 0;
        bar.dataset.progress = pct;
        bar.style.width      = pct + "%";
    }

    const completeMsg = document.querySelector(".summary-complete");
    if (done === total && total > 0) {
        if (!completeMsg) {
            const p = document.createElement("p");
            p.className   = "summary-complete";
            p.textContent = "🏆 All habits complete for today!";
            document.querySelector(".summary-section").appendChild(p);
        }
    } else {
        if (completeMsg) completeMsg.remove();
    }
}


// ── UPDATE HABIT CARD UI ──
function updateHabitCard(card, data) {
    const habitId = card.dataset.id;

    // Completions today
    const compEl = card.querySelector(".completions-today");
    if (compEl) compEl.textContent = `✅ ${data.completions_today}× today`;

    // Streak
    const streakEl = card.querySelector(".streak-display");
    if (streakEl) streakEl.textContent = `🔥 ${data.streak} day streak`;

    // XP display — always update regardless of multiplier value
    const xpEl = card.querySelector(".xp-display");
    if (xpEl && data.multiplier !== undefined) {
        if (data.multiplier > 1) {
            xpEl.innerHTML =
                `<span class="xp-boosted">${data.boosted_xp} XP</span>` +
                `<span class="xp-multiplier">×${data.multiplier.toFixed(2)}</span>`;
        } else {
            xpEl.textContent = `${data.boosted_xp} XP`;
        }
    }

    // Checkbox state — checked if completions > 0
    const checkbox = card.querySelector(".habit-checkbox");
    if (checkbox) checkbox.checked = data.completions_today > 0;

    // Freeze icons
    const freezeRow = card.querySelector(".freeze-row");
    if (freezeRow) {
        if (data.streak_freezes > 0) {
            let html = "";
            for (let i = 0; i < data.streak_freezes; i++) {
                html += `<span class="freeze-icon">🧊</span>`;
            }
            html += ` <span class="freeze-label">× ${data.streak_freezes}</span>`;
            freezeRow.innerHTML = html;
        } else {
            freezeRow.innerHTML =
                `<span class="freeze-empty">No freezes — earn 1 per 5 completions</span>`;
        }
    }

    // Update week-strip today cell
    const todayStrip = card.querySelector(".week-strip-today");
    if (todayStrip) {
        if (data.completions_today > 0) {
            todayStrip.classList.add("week-strip-done");
        } else {
            todayStrip.classList.remove("week-strip-done");
        }
    }

    // Update weekly overview grid cell for this habit
    const weeklyRow = document.querySelector(`.weekly-row[data-habit-id="${habitId}"]`);
    if (weeklyRow) {
        const todayCell = weeklyRow.querySelector(".weekly-cell-today");
        if (todayCell) {
            if (data.completions_today > 0) {
                todayCell.classList.add("weekly-cell-done");
                todayCell.textContent = "✓";
            } else {
                todayCell.classList.remove("weekly-cell-done");
                todayCell.textContent = "";
            }
        }
    }

    // Update player XP display globally
    if (data.total_xp !== undefined) {
        const xpDisplay = document.querySelector(".player-xp");
        if (xpDisplay) xpDisplay.textContent = `Total XP: ${data.total_xp}`;

        const levelDisplay = document.querySelector(".player-level");
        if (levelDisplay) levelDisplay.textContent = `Level: ${data.level}`;

        // Update the XP progress bar
        const bar = document.querySelector(".progress-bar");
        if (bar && data.progress_percent !== undefined) {
            bar.dataset.progress = data.progress_percent;
            bar.style.width      = data.progress_percent + "%";
        }

        // Update the % label
        const pctLabel = document.querySelector(".progress-label");
        if (pctLabel && data.progress_percent !== undefined) {
            pctLabel.textContent =
                `${data.progress_percent}% to Level ${data.level + 1}`;
        }
    }

    // Update daily summary bar
    if (data.completed_count !== undefined && data.total_habits !== undefined) {
        updateDailySummary(data.completed_count, data.total_habits);
    }
}


// ── HABIT CHECKBOX ──
// Check   → complete
// Uncheck → undo
document.addEventListener("change", async function(e) {
    const checkbox = e.target.closest(".habit-checkbox");
    if (!checkbox) return;

    const card    = checkbox.closest(".habit-card");
    const habitId = card.dataset.id;

    const fd = new FormData();
    fd.append("note", "");

    const url  = checkbox.checked
        ? `/complete/${habitId}`
        : `/undo_habit/${habitId}`;

    const data = await postForm(url, fd);

    if (data.messages) {
        data.messages.forEach(m => showFlash(m.category, m.text));
    }
    if (data.ok) {
        updateHabitCard(card, data);
    } else {
        // Revert checkbox if something went wrong
        checkbox.checked = !checkbox.checked;
    }
});


// ── +1 / -1 BUTTONS ──
document.addEventListener("click", async function(e) {
    // +1 opens note modal — handled separately
    const minusBtn = e.target.closest(".btn-minus");
    if (!minusBtn) return;

    const card    = minusBtn.closest(".habit-card");
    const habitId = card.dataset.id;
    const fd      = new FormData();

    const data = await postForm(`/undo_habit/${habitId}`, fd);
    if (data.messages) {
        data.messages.forEach(m => showFlash(m.category, m.text));
    }
    if (data.ok) updateHabitCard(card, data);
});


// ── PIN BUTTON ──
document.addEventListener("click", async function(e) {
    const pinBtn = e.target.closest(".btn-pin");
    if (!pinBtn) return;

    e.preventDefault();
    const card    = pinBtn.closest(".habit-card");
    const habitId = card.dataset.id;
    const fd      = new FormData();

    const data = await postForm(`/pin/${habitId}`, fd);
    if (data.ok) {
        pinBtn.textContent = data.pinned ? "📌" : "📍";
        const indicator = card.querySelector(".pin-indicator");
        if (data.pinned) {
            if (!indicator) {
                const h3 = card.querySelector("h3");
                const span = document.createElement("span");
                span.className = "pin-indicator";
                span.title     = "Pinned";
                span.textContent = "📌";
                h3.prepend(span);
            }
        } else {
            if (indicator) indicator.remove();
        }
    }
});


// ── SKIP BUTTON ──
document.addEventListener("click", async function(e) {
    const skipBtn = e.target.closest(".btn-skip");
    if (!skipBtn) return;

    const card    = skipBtn.closest(".habit-card");
    const habitId = card.dataset.id;
    const fd      = new FormData();

    const data = await postForm(`/skip/${habitId}`, fd);
    if (data.messages) {
        data.messages.forEach(m => showFlash(m.category, m.text));
    }
    if (data.ok) {
        skipBtn.disabled    = true;
        skipBtn.textContent = "⏭️ Skipped";
    }
});


// ── NOTE MODAL ──
function openNoteModal(habitId) {
    const modal = document.getElementById("note-modal");
    const form  = document.getElementById("note-form");
    form.dataset.habitId = habitId;
    modal.style.display  = "flex";
    modal.querySelector("textarea").focus();
}

function closeNoteModal() {
    document.getElementById("note-modal").style.display = "none";
    document.getElementById("note-form").querySelector("textarea").value = "";
}

document.getElementById("note-modal")?.addEventListener("click", function(e) {
    if (e.target === this) closeNoteModal();
});

// Note form submit — AJAX complete
document.getElementById("note-form")?.addEventListener("submit", async function(e) {
    e.preventDefault();
    const habitId = this.dataset.habitId;
    const fd      = new FormData(this);

    const data = await postForm(`/complete/${habitId}`, fd);

    closeNoteModal();

    if (data.messages) {
        data.messages.forEach(m => showFlash(m.category, m.text));
    }

    if (data.ok) {
        const card = document.querySelector(`.habit-card[data-id="${habitId}"]`);
        if (card) updateHabitCard(card, data);
    }
});


// ── REDEEM CONFIRM ──
function confirmRedeem(name, cost, currentXp) {
    const remaining = currentXp - cost;
    return confirm(
        `Redeem "${name}" for ${cost} XP?\n` +
        `You have ${currentXp} XP — you'll have ${remaining} XP remaining.`
    );
}


// ── DRAG TO REORDER ──
const habitList = document.getElementById("habit-list");
let draggedEl   = null;

if (habitList) {
    habitList.addEventListener("dragstart", e => {
        draggedEl = e.target.closest(".habit-card");
        if (draggedEl) draggedEl.classList.add("dragging");
    });

    habitList.addEventListener("dragend", () => {
        if (draggedEl) draggedEl.classList.remove("dragging");
        draggedEl = null;
        saveOrder();
    });

    habitList.addEventListener("dragover", e => {
        e.preventDefault();
        const target = e.target.closest(".habit-card");
        if (!target || target === draggedEl) return;
        const rect   = target.getBoundingClientRect();
        const before = e.clientY < rect.top + rect.height / 2;
        habitList.insertBefore(
            draggedEl,
            before ? target : target.nextSibling
        );
    });
}

function saveOrder() {
    const ids = Array.from(
        document.querySelectorAll(".habit-card[data-id]")
    ).map(c => c.dataset.id).join(",");

    fetch("/reorder", {
        method:  "POST",
        headers: {"Content-Type": "application/x-www-form-urlencoded"},
        body:    `order=${ids}`,
    });
}