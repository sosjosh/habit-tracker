console.log("Habit Quest Loaded")
const progressBar = document.querySelector(".progress-bar")

if (progressBar) {
    const progress = progressBar.dataset.progress
    progressBar.style.width = progress + "%"
}