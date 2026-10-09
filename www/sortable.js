// Click a .sortable-table header to sort by that column (see viz.sortable_table): numbers sort
// on their data-v value, text alphabetically, and rows marked .pinned stay on top.
document.addEventListener("click", function (e) {
  const th = e.target.closest(".sortable-table th");
  if (!th) return;
  const table = th.closest("table"), tbody = table.querySelector("tbody");
  const idx = Array.from(th.parentNode.children).indexOf(th);
  const asc = th.dataset.dir !== "asc";
  table.querySelectorAll("th").forEach(h => { h.dataset.dir = ""; h.classList.remove("asc", "desc"); });
  th.dataset.dir = asc ? "asc" : "desc"; th.classList.add(asc ? "asc" : "desc");
  const rows = Array.from(tbody.rows), pinned = rows.filter(r => r.classList.contains("pinned"));
  const key = r => { const c = r.cells[idx]; return "v" in c.dataset ? (c.dataset.v === "" ? null : +c.dataset.v) : c.textContent; };
  const sorted = rows.filter(r => !pinned.includes(r)).sort((a, b) => {
    const x = key(a), y = key(b);
    if (x === null) return 1; if (y === null) return -1;
    const d = typeof x === "number" ? x - y : String(x).localeCompare(String(y));
    return asc ? d : -d;
  });
  pinned.concat(sorted).forEach(r => tbody.appendChild(r));
});
