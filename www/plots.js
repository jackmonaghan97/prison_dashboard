// Plotly's `responsive` config only listens to window resizes. Charts drawn while their
// nav panel is hidden (width 0) or when the sidebar collapses also need a re-fit, so
// watch every card's size and resize the plots inside it.
(function () {
  const timers = new WeakMap();
  function refit(el) {
    if (!window.Plotly || !el._fullLayout || !el.offsetWidth) return;
    clearTimeout(timers.get(el));
    timers.set(el, setTimeout(() => Plotly.Plots.resize(el), 100));
  }
  const ro = new ResizeObserver(entries => entries.forEach(e =>
    e.target.querySelectorAll(".plotly-chart").forEach(refit)));
  function observeAll() {
    document.querySelectorAll(".plotly-chart").forEach(el => {
      const box = el.closest(".card") || el.parentElement;
      if (box && !box.dataset.plotRo) { box.dataset.plotRo = "1"; ro.observe(box); }
    });
  }
  document.addEventListener("shiny:value", () => setTimeout(observeAll, 50));
  document.addEventListener("shown.bs.tab", () =>
    document.querySelectorAll(".plotly-chart").forEach(refit));
})();
