console.log("Habit Quest Loaded");

// Progress bar
const progressBar = document.querySelector(".progress-bar");
if (progressBar) {
    const progress = progressBar.dataset.progress;
    progressBar.style.width = progress + "%";
}

// Auto-dismiss flash messages after 4 seconds
setTimeout(() => {
    document.querySelectorAll(".flash").forEach(el => {
        el.style.transition = "opacity 0.5s ease";
        el.style.opacity = "0";
        setTimeout(() => el.remove(), 500);
    });
}, 4000);