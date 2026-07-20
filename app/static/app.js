const state = {
  teams: [],
  view: "total",
  basis: "adjusted",
  perGame: false,
  order: "high",
};

const elements = {
  season: document.querySelector("#season"),
  force: document.querySelector("#force"),
  refresh: document.querySelector("#refresh"),
  statusText: document.querySelector("#status-text"),
  statusDetail: document.querySelector("#status-detail"),
  statusStrip: document.querySelector(".status-strip"),
  framing: document.querySelector("#framing"),
  basis: document.querySelector("#basis"),
  basisWrap: document.querySelector("#basis-wrap"),
  order: document.querySelector("#order"),
  perGame: document.querySelector("#per-game"),
  perGameWrap: document.querySelector("#per-game-wrap"),
  heading: document.querySelector("#metric-heading"),
  rows: document.querySelector("#team-rows"),
  leagueTotal: document.querySelector("#league-total"),
  leagueSpShare: document.querySelector("#league-sp-share"),
  leagueReclassified: document.querySelector("#league-reclassified"),
  leagueReview: document.querySelector("#league-review"),
};

elements.season.value = new Date().getFullYear();
const integer = new Intl.NumberFormat("en-US");
const decimal = new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

function roleKey(role) {
  return `${state.basis}_${role}`;
}

function rawMetric(team) {
  if (state.view === "total") return team.total;
  if (state.view === "sp") return team[roleKey("sp")];
  if (state.view === "rp") return team[roleKey("rp")];
  if (state.view === "share") return team[roleKey("rp")] / team.total;
  return team.adjusted_sp - team.official_sp;
}

function metric(team) {
  const value = rawMetric(team);
  return state.perGame && state.view !== "share" ? value / team.games : value;
}

function formatMetric(value) {
  if (state.view === "share") return `${decimal.format(value * 100)}%`;
  if (state.perGame) return decimal.format(value);
  const rounded = Math.round(value);
  if (state.view === "adjustment" && rounded > 0) return `+${integer.format(rounded)}`;
  return integer.format(rounded);
}

function signed(value) {
  if (Math.abs(value) < 0.05) return "0.0";
  return `${value > 0 ? "+" : "−"}${decimal.format(Math.abs(value))}`;
}

function leagueTotals() {
  return state.teams.reduce(
    (sum, team) => {
      for (const key of ["total", "official_sp", "official_rp", "adjusted_sp", "adjusted_rp", "bulk_to_sp", "opener_to_rp", "review_count"]) {
        sum[key] += Number(team[key] || 0);
      }
      return sum;
    },
    { total: 0, official_sp: 0, official_rp: 0, adjusted_sp: 0, adjusted_rp: 0, bulk_to_sp: 0, opener_to_rp: 0, review_count: 0 },
  );
}

function context(team, league) {
  if (state.view === "total") {
    return `${decimal.format((team.adjusted_sp / team.total) * 100)}% SP · ${decimal.format((team.adjusted_rp / team.total) * 100)}% RP`;
  }
  if (state.view === "sp" || state.view === "rp") {
    const key = roleKey(state.view);
    const share = team[key] / team.total;
    const leagueShare = league[key] / league.total;
    return `${decimal.format(share * 100)}% of team total · ${signed((share - leagueShare) * 100)} pp vs MLB`;
  }
  if (state.view === "share") {
    const share = team[roleKey("rp")] / team.total;
    const leagueShare = league[roleKey("rp")] / league.total;
    return `${decimal.format((1 - share) * 100)}% SP · ${signed((share - leagueShare) * 100)} pp vs MLB`;
  }
  return `${integer.format(team.bulk_to_sp)} bulk → SP · ${integer.format(team.opener_to_rp)} opener → RP`;
}

function labels() {
  const suffix = state.perGame && state.view !== "share" ? " per game" : "";
  if (state.view === "total") return `Total pitches${suffix}`;
  if (state.view === "sp") return `SP pitches${suffix}`;
  if (state.view === "rp") return `RP pitches${suffix}`;
  if (state.view === "share") return "Bullpen share";
  return `Net SP reclassification${suffix}`;
}

function cell(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function render() {
  const roleView = ["sp", "rp", "share"].includes(state.view);
  elements.basisWrap.hidden = !roleView;
  elements.perGameWrap.hidden = state.view === "share";
  if (state.view === "share") {
    state.perGame = false;
    elements.perGame.checked = false;
  }
  elements.heading.textContent = labels();

  const league = leagueTotals();
  elements.leagueTotal.textContent = league.total ? integer.format(league.total) : "—";
  elements.leagueSpShare.textContent = league.total ? `${decimal.format((league.adjusted_sp / league.total) * 100)}%` : "—";
  elements.leagueReclassified.textContent = integer.format(league.bulk_to_sp + league.opener_to_rp);
  elements.leagueReview.textContent = integer.format(league.review_count);

  elements.framing.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === state.view);
  });

  if (!state.teams.length) {
    elements.rows.replaceChildren();
    const row = document.createElement("tr");
    const empty = cell("td", "empty", "No cached data yet. Run a refresh to populate the dashboard.");
    empty.colSpan = 4;
    row.append(empty);
    elements.rows.append(row);
    return;
  }

  const ranked = [...state.teams]
    .sort((a, b) => rawMetric(b) - rawMetric(a) || a.team_name.localeCompare(b.team_name))
    .map((team, index) => ({ ...team, rank: index + 1 }));
  let ordered = ranked;
  if (state.order === "low") ordered = [...ranked].sort((a, b) => rawMetric(a) - rawMetric(b));
  if (state.order === "alpha") ordered = [...ranked].sort((a, b) => a.team_name.localeCompare(b.team_name));
  const maximum = Math.max(...ordered.map((team) => Math.abs(metric(team))), 1);

  const fragments = ordered.map((team) => {
    const row = document.createElement("tr");
    row.append(cell("td", "rank", String(team.rank)));
    row.append(cell("td", "team", team.team_name));

    const metricCell = cell("td");
    const metricWrap = cell("div", "metric");
    metricWrap.append(cell("strong", "", formatMetric(metric(team))));
    const track = cell("span", "track");
    const fill = cell("span", "fill");
    fill.style.width = `${Math.max(2, (Math.abs(metric(team)) / maximum) * 100)}%`;
    track.append(fill);
    metricWrap.append(track);
    metricCell.append(metricWrap);
    row.append(metricCell);
    row.append(cell("td", "context secondary", context(team, league)));
    return row;
  });
  elements.rows.replaceChildren(...fragments);
}

async function loadTeams() {
  const response = await fetch(`/api/teams?season=${encodeURIComponent(elements.season.value)}`);
  if (!response.ok) throw new Error(`Team data request failed (${response.status})`);
  const payload = await response.json();
  state.teams = payload.teams;
  render();
}

function formatStatus(status) {
  if (status.running) {
    const progress = status.games_total ? `${status.games_processed}/${status.games_total} games` : status.phase;
    elements.statusText.textContent = `Refreshing ${status.season}: ${progress}`;
    elements.statusDetail.textContent = `${integer.format(status.api_calls || 0)} API calls`;
    elements.statusStrip.classList.remove("failed");
    return;
  }
  if (status.error) {
    elements.statusText.textContent = `Refresh failed: ${status.error}`;
    elements.statusDetail.textContent = `${integer.format(status.api_calls || 0)} API calls`;
    elements.statusStrip.classList.add("failed");
    return;
  }
  elements.statusStrip.classList.remove("failed");
  elements.statusText.textContent = status.last_refresh_at ? `Last refreshed ${new Date(status.last_refresh_at).toLocaleString()}` : "No refresh has run yet";
  const skipped = Number(status.last_games_failed || 0);
  const skippedNote = skipped ? ` · ${integer.format(skipped)} games skipped (retry to backfill)` : "";
  elements.statusDetail.textContent = status.last_api_calls !== undefined ? `${integer.format(status.last_api_calls)} API calls · ${integer.format(status.completed_games || 0)} completed games${skippedNote}` : "";
}

async function pollStatus() {
  const response = await fetch("/api/status");
  const status = await response.json();
  formatStatus(status);
  elements.refresh.disabled = Boolean(status.running);
  if (status.running) {
    window.setTimeout(pollStatus, 1200);
  } else {
    await loadTeams();
  }
}

elements.refresh.addEventListener("click", async () => {
  elements.refresh.disabled = true;
  const response = await fetch("/api/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ season: Number(elements.season.value), force: elements.force.checked }),
  });
  if (!response.ok) {
    const payload = await response.json();
    elements.statusText.textContent = payload.detail || "Refresh request failed";
    elements.refresh.disabled = false;
    return;
  }
  await pollStatus();
});

elements.season.addEventListener("change", loadTeams);
elements.framing.addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (!button) return;
  state.view = button.dataset.view;
  render();
});
elements.basis.addEventListener("change", () => { state.basis = elements.basis.value; render(); });
elements.order.addEventListener("change", () => { state.order = elements.order.value; render(); });
elements.perGame.addEventListener("change", () => { state.perGame = elements.perGame.checked; render(); });

pollStatus().catch((error) => {
  elements.statusText.textContent = error.message;
  elements.statusStrip.classList.add("failed");
});

