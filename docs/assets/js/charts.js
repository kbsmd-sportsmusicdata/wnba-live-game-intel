(function () {
  function clampPercent(value) {
    if (!Number.isFinite(value)) {
      return 0;
    }
    return Math.max(0, Math.min(100, value));
  }

  function formatPct(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "--";
    }
    return `${(Number(value) * 100).toFixed(1)}%`;
  }

  function renderFourFactorsChart(container, fourFactors) {
    if (!container) {
      return;
    }
    const rows = Array.isArray(fourFactors?.wide) ? fourFactors.wide : [];
    if (!rows.length) {
      container.innerHTML = '<div class="empty-state">Four Factors data is not available for this run.</div>';
      return;
    }

    const html = rows
      .map((row) => {
        const leftValue = Number(row.team_a_value || 0);
        const rightValue = Number(row.team_b_value || 0);
        const total = Math.abs(leftValue) + Math.abs(rightValue) || 1;
        const leftWidth = clampPercent((Math.abs(leftValue) / total) * 100);
        const rightWidth = clampPercent((Math.abs(rightValue) / total) * 100);
        return `
          <div class="factor-row">
            <div class="mini-label">${row.factor_label || row.factor}</div>
            <div class="factor-track">
              <div class="factor-bar team-a"><span style="width:${leftWidth}%"></span></div>
              <div class="factor-value">${formatPct(row.team_a_value)}</div>
              <div class="factor-bar team-b"><span style="width:${rightWidth}%"></span></div>
            </div>
            <div class="subtle">Winner: <strong>${row.winning_team || "N/A"}</strong></div>
          </div>
        `;
      })
      .join("");

    container.innerHTML = `<div class="factor-bars">${html}</div>`;
  }

  window.LiveGameCharts = {
    renderFourFactorsChart,
    formatPct,
  };
})();
