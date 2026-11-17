(() => {
  "use strict";

  const grid = document.querySelector(".thoughts-grid");
  if (!grid) return;

  const notes = Array.from(grid.querySelectorAll(".thoughts-note"));
  const timestamp = (value) => {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : 0;
  };

  notes.sort((left, right) => {
    const dateOrder = right.dataset.date.localeCompare(left.dataset.date);
    if (dateOrder) return dateOrder;
    return timestamp(right.dataset.createdAt) - timestamp(left.dataset.createdAt)
      || left.dataset.noteId.localeCompare(right.dataset.noteId);
  });

  notes.forEach((note) => {
    let hash = 2166136261;
    for (const character of note.dataset.noteId) {
      hash = Math.imul(hash ^ character.charCodeAt(0), 16777619);
    }
    hash >>>= 0;
    note.dataset.tone = String(hash % 4);
    note.style.setProperty("--note-rotation", `${((hash % 9) - 4) * 0.18}deg`);
    grid.append(note);
  });
})();
