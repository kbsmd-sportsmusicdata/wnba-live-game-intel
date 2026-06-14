(function () {
  const DATA_URL = "./dashboard_data/dashboard_payload.json";
  const SUMMARY_URL = "./dashboard_data/game_summary.json";

  const SORTABLE_COLUMNS = {
    player_name: "string",
    team_abbr: "string",
    starter_label: "string",
    minutes: "number",
    pts: "number",
    reb: "number",
    ast: "number",
    tov: "number",
    pf: "number",
    plus_minus: "number",
    efg_pct: "number",
    ts_pct: "number",
    usg_pct: "number",
    game_score: "number",
  };

  let currentSort = { key: "game_score", direction: "desc" };
  let cachedPayload = null;

  function formatPct(value) {
    return window.LiveGameCharts.formatPct(value);
  }

  function formatNumber(value, digits = 1) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) {
      return "--";
    }
    return Number(value).toFixed(digits);
  }

  function safeArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function renderEmptyState(message) {
    return `<div class="empty-state">${message}</div>`;
  }

  function getLeaderOrEmpty(items) {
    return safeArray(items)[0] || null;
  }

  function renderHero(summary, payload) {
    const hero = document.getElementById("hero-status");
    if (!hero) {
      return;
    }

    const game = payload.game || {};
    hero.innerHTML = `
      <div>
        <span class="mini-label">Current State</span>
        <span class="value">${summary.game_status || game.game_status || "Unavailable"}</span>
      </div>
      <div class="meta-grid">
        <div class="meta-card">
          <span class="stat-label">Leader</span>
          <span class="value">${summary.winner_team_abbr || game.winner_team_abbr || "--"}</span>
        </div>
        <div class="meta-card">
          <span class="stat-label">Margin</span>
          <span class="value">${summary.final_margin ?? game.final_margin ?? "--"}</span>
        </div>
        <div class="meta-card">
          <span class="stat-label">WPBA</span>
          <span class="value">${summary.wpba_scoreline_text || "Not available"}</span>
        </div>
        <div class="meta-card">
          <span class="stat-label">Updated</span>
          <span class="value">${summary.last_updated || payload.metadata?.generated_at || "--"}</span>
        </div>
      </div>
    `;
  }

  function renderCommandCenter(summary, payload) {
    const game = payload.game || {};
    return `
      <section class="panel panel-wide">
        <h2>Game Command Center</h2>
        <div class="scoreboard">
          <div class="score-team">
            <span class="label">${summary.away_team_abbr || game.away_team_abbr || "Away"}</span>
            <span class="value">${summary.away_pts ?? game.away_pts ?? "--"}</span>
          </div>
          <div class="score-divider">
            <span class="status-pill"><span class="status-dot"></span>${summary.game_status || game.game_status || "Unknown"}</span>
            <p class="subtle">Period ${summary.period ?? game.period ?? "--"} · Clock ${summary.clock ?? game.clock ?? "--"}</p>
          </div>
          <div class="score-team">
            <span class="label">${summary.home_team_abbr || game.home_team_abbr || "Home"}</span>
            <span class="value">${summary.home_pts ?? game.home_pts ?? "--"}</span>
          </div>
        </div>
        <div class="meta-grid">
          <div class="meta-card">
            <span class="stat-label">Winner / Leader</span>
            <span class="value">${summary.winner_team_abbr || game.winner_team_abbr || "--"}</span>
          </div>
          <div class="meta-card">
            <span class="stat-label">Final Margin</span>
            <span class="value">${summary.final_margin ?? game.final_margin ?? "--"}</span>
          </div>
          <div class="meta-card">
            <span class="stat-label">WPBA Scoreline</span>
            <span class="value">${summary.wpba_scoreline_text || "Not available"}</span>
          </div>
          <div class="meta-card">
            <span class="stat-label">Last Updated</span>
            <span class="value">${summary.last_updated || payload.metadata?.generated_at || "--"}</span>
          </div>
        </div>
      </section>
    `;
  }

  function renderWpbaPanel(payload) {
    if (!payload.wpba || !Object.keys(payload.wpba).length) {
      return "";
    }
    const wpba = payload.wpba;
    const quarters = safeArray(wpba.quarter_breakdown)
      .map((quarter) => `
        <div class="quarter-row">
          <span>Q${quarter.quarter}</span>
          <span>${quarter.winner_team_abbr || "TIE"} won ${quarter.home_wpba_points ?? 0}-${quarter.away_wpba_points ?? 0}</span>
        </div>
      `)
      .join("");

    return `
      <section class="panel">
        <h2>WPBA Points Race</h2>
        <div class="wpba-grid">
          <div class="wpba-card">
            <span class="stat-label">Scoreline</span>
            <strong>${wpba.scoreline_text || "Not available"}</strong>
            <div class="detail">${wpba.format_name || "WPBA scoring"} · ${wpba.available_points ?? 7} total points</div>
          </div>
          <div class="wpba-card">
            <span class="stat-label">Quarter Wins</span>
            <strong>${wpba.away_quarters_won ?? 0} away · ${wpba.home_quarters_won ?? 0} home</strong>
            <div class="detail">${wpba.tied_quarters ?? 0} tied quarters</div>
          </div>
          <div class="wpba-card">
            <span class="stat-label">Game-Win Points</span>
            <strong>${formatNumber(wpba.away_game_win_points ?? 0, 1)} away · ${formatNumber(wpba.home_game_win_points ?? 0, 1)} home</strong>
          </div>
          <div class="wpba-card">
            <span class="stat-label">Quarter Points</span>
            <strong>${formatNumber(wpba.away_quarter_points ?? 0, 1)} away · ${formatNumber(wpba.home_quarter_points ?? 0, 1)} home</strong>
          </div>
        </div>
        <div class="quarter-list">
          ${quarters || '<div class="empty-state">Quarter breakdown is not available.</div>'}
        </div>
      </section>
    `;
  }

  function renderTeamCards(payload) {
    const cards = safeArray(payload.teams);
    return `
      <section class="panel">
        <h2>Team Snapshot Cards</h2>
        <div class="team-card-grid">
          ${cards.length ? cards.map((team) => `
            <article class="team-card">
              <header>
                <div>
                  <span class="mini-label">${team.home_away || ""}</span>
                  <div class="team-name">${team.team_abbr}</div>
                </div>
                <span class="badge ${team.is_winner ? "win" : ""}">${team.is_winner ? "Winner" : "In chase"}</span>
              </header>
              <div class="stat-grid">
                <div class="stat-cell"><span class="stat-label">PTS</span><span class="value">${team.points ?? "--"}</span></div>
                <div class="stat-cell"><span class="stat-label">eFG%</span><span class="value">${formatPct(team.efg_pct)}</span></div>
                <div class="stat-cell"><span class="stat-label">TS%</span><span class="value">${formatPct(team.ts_pct)}</span></div>
                <div class="stat-cell"><span class="stat-label">Poss</span><span class="value">${formatNumber(team.possessions, 1)}</span></div>
                <div class="stat-cell"><span class="stat-label">ORtg</span><span class="value">${formatNumber(team.ortg, 1)}</span></div>
                <div class="stat-cell"><span class="stat-label">DRtg</span><span class="value">${formatNumber(team.drtg, 1)}</span></div>
                <div class="stat-cell"><span class="stat-label">Net</span><span class="value">${formatNumber(team.net_rtg, 1)}</span></div>
                <div class="stat-cell"><span class="stat-label">Pace</span><span class="value">${formatNumber(team.pace, 1)}</span></div>
                <div class="stat-cell"><span class="stat-label">WPBA</span><span class="value">${formatNumber(team.wpba_total_points, 1)}</span></div>
                <div class="stat-cell"><span class="stat-label">REB</span><span class="value">${team.rebounds ?? "--"}</span></div>
                <div class="stat-cell"><span class="stat-label">TOV</span><span class="value">${team.turnovers ?? "--"}</span></div>
                <div class="stat-cell"><span class="stat-label">PF</span><span class="value">${team.fouls ?? "--"}</span></div>
              </div>
            </article>
          `).join("") : renderEmptyState("Team snapshot data is not available.")}
        </div>
      </section>
    `;
  }

  function renderFourFactors(payload) {
    const longRows = safeArray(payload.four_factors?.long);
    const wideRows = safeArray(payload.four_factors?.wide);
    const detailCards = wideRows.map((row) => `
      <div class="factor-card">
        <span class="stat-label">${row.factor_label || row.factor}</span>
        <div class="detail">${row.team_a_abbr}: ${formatPct(row.team_a_value)} · ${row.team_b_abbr}: ${formatPct(row.team_b_value)}</div>
        <div class="winner">${row.winning_team || "N/A"} is winning this factor</div>
      </div>
    `).join("");

    return `
      <section class="panel panel-wide">
        <h2>Four Factors Comparison</h2>
        <div class="factors-wrap">
          <div id="four-factors-chart"></div>
          <div>${detailCards || renderEmptyState("Four Factors details are not available.")}</div>
        </div>
      </section>
    `;
  }

  function sortPlayers(players) {
    const { key, direction } = currentSort;
    const type = SORTABLE_COLUMNS[key] || "number";
    const sorted = [...players].sort((a, b) => {
      const left = a[key];
      const right = b[key];
      if (type === "string") {
        const result = String(left || "").localeCompare(String(right || ""));
        return direction === "asc" ? result : -result;
      }
      const result = Number(left || 0) - Number(right || 0);
      return direction === "asc" ? result : -result;
    });
    return sorted;
  }

  function renderPlayerTable(payload) {
    const players = sortPlayers(safeArray(payload.players));
    const headers = [
      ["player_name", "Player"],
      ["team_abbr", "Team"],
      ["starter_label", "Role"],
      ["minutes", "MIN"],
      ["pts", "PTS"],
      ["reb", "REB"],
      ["ast", "AST"],
      ["tov", "TOV"],
      ["pf", "PF"],
      ["plus_minus", "+/-"],
      ["efg_pct", "eFG%"],
      ["ts_pct", "TS%"],
      ["usg_pct", "USG%"],
      ["game_score", "Game Score"],
      ["ast_to_display", "AST/TO"],
      ["foul_status", "Foul Status"],
    ];

    const body = players.length
      ? players.map((player) => `
          <tr>
            <td>${player.player_name || "--"}</td>
            <td>${player.team_abbr || "--"}</td>
            <td><span class="pill ${player.starter ? "starter" : "bench"}">${player.starter_label}</span></td>
            <td>${formatNumber(player.minutes, 1)}</td>
            <td>${player.pts ?? "--"}</td>
            <td>${player.reb ?? "--"}</td>
            <td>${player.ast ?? "--"}</td>
            <td>${player.tov ?? "--"}</td>
            <td>${player.pf ?? "--"}</td>
            <td>${player.plus_minus ?? "--"}</td>
            <td>${formatPct(player.efg_pct)}</td>
            <td>${formatPct(player.ts_pct)}</td>
            <td>${formatPct(player.usg_pct)}</td>
            <td><span class="pill ${player.game_score >= 15 ? "highlight" : ""}">${formatNumber(player.game_score, 1)}</span></td>
            <td>${player.ast_to_display}</td>
            <td><span class="pill ${player.foul_status}">${player.foul_status.replace("_", " ")}</span></td>
          </tr>
        `).join("")
      : `<tr><td colspan="${headers.length}">${renderEmptyState("No player rows are available for this run.")}</td></tr>`;

    return `
      <section class="panel panel-wide">
        <h2>Player Advanced Box Score</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                ${headers.map(([key, label]) => `
                  <th><button data-sort-key="${key}" type="button">${label}</button></th>
                `).join("")}
              </tr>
            </thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      </section>
    `;
  }

  function renderFoulBoard(payload) {
    const rows = safeArray(payload.leaders?.foul_trouble);
    return `
      <section class="panel">
        <h2>Foul Trouble Board</h2>
        <div class="foul-board">
          ${rows.length ? rows.map((player) => `
            <article class="note-card">
              <strong>${player.player_name} · ${player.team_abbr}</strong>
              <div class="detail">PF ${player.pf} · ${player.foul_status.replace("_", " ")} · ${formatNumber(player.minutes, 1)} minutes · Game Score ${formatNumber(player.game_score, 1)}</div>
            </article>
          `).join("") : renderEmptyState("No players are currently flagged for foul trouble.")}
        </div>
      </section>
    `;
  }

  function renderImpactLeaders(payload) {
    const groups = [
      ["Scoring Leader", getLeaderOrEmpty(payload.leaders?.points)],
      ["Game Score Leader", getLeaderOrEmpty(payload.leaders?.game_score)],
      ["Top Usage", getLeaderOrEmpty(payload.leaders?.usage)],
      ["Top Efficiency", getLeaderOrEmpty(payload.leaders?.efficiency)],
      ["Top Bench Impact", getLeaderOrEmpty(payload.leaders?.bench_impact)],
      ["Top Passer", getLeaderOrEmpty(payload.leaders?.assists)],
    ];
    return `
      <section class="panel">
        <h2>Impact Leaders</h2>
        <div class="leaders-grid">
          ${groups.map(([label, player]) => player ? `
            <article class="leader-card">
              <span class="stat-label">${label}</span>
              <span class="value">${player.player_name}</span>
              <div class="detail">${player.team_abbr} · ${player.pts ?? 0} PTS · GS ${formatNumber(player.game_score, 1)} · TS ${formatPct(player.ts_pct)}</div>
            </article>
          ` : `<div class="empty-state">${label} not available.</div>`).join("")}
        </div>
      </section>
    `;
  }

  function renderNotes(payload) {
    const storylines = safeArray(payload.broadcast_storylines).slice(0, 5);
    const flags = safeArray(payload.insight_flags).slice(0, 5);
    return `
      <section class="panel">
        <h2>Broadcast / Coach Notes</h2>
        <div class="notes-list">
          ${storylines.map((line) => `<article class="note-card"><strong>Storyline</strong><div class="detail">${line}</div></article>`).join("")}
          ${flags.map((flag) => `<article class="note-card"><strong>${flag.flag_type.replace(/_/g, " ")}</strong><div class="detail">${flag.message}</div></article>`).join("")}
          ${!storylines.length && !flags.length ? renderEmptyState("No broadcast or coach notes are available for this run.") : ""}
        </div>
      </section>
    `;
  }

  function bindSorting(app) {
    app.querySelectorAll("[data-sort-key]").forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.getAttribute("data-sort-key");
        if (!key) {
          return;
        }
        if (currentSort.key === key) {
          currentSort.direction = currentSort.direction === "asc" ? "desc" : "asc";
        } else {
          currentSort = { key, direction: "desc" };
        }
        renderDashboard(cachedPayload.payload, cachedPayload.summary);
      });
    });
  }

  function renderDashboard(payload, summary) {
    cachedPayload = { payload, summary };
    renderHero(summary, payload);

    const app = document.getElementById("app");
    if (!app) {
      return;
    }

    app.innerHTML = [
      renderCommandCenter(summary, payload),
      renderWpbaPanel(payload),
      renderTeamCards(payload),
      renderFourFactors(payload),
      renderPlayerTable(payload),
      renderFoulBoard(payload),
      renderImpactLeaders(payload),
      renderNotes(payload),
    ].join("");

    window.LiveGameCharts.renderFourFactorsChart(
      document.getElementById("four-factors-chart"),
      payload.four_factors
    );
    bindSorting(app);
  }

  function renderError(message) {
    const app = document.getElementById("app");
    if (!app) {
      return;
    }
    app.innerHTML = `
      <section class="panel error-card">
        <h2>Dashboard Data Error</h2>
        <p>${message}</p>
      </section>
    `;
  }

  async function init() {
    try {
      const [payloadResponse, summaryResponse] = await Promise.all([
        fetch(DATA_URL),
        fetch(SUMMARY_URL),
      ]);
      const payload = await payloadResponse.json();
      const summary = await summaryResponse.json();
      renderDashboard(payload, summary);
    } catch (error) {
      renderError("The dashboard could not load its generated JSON payloads. Confirm docs/dashboard_data/*.json exists for this branch.");
      console.error(error);
    }
  }

  init();
})();
