import { useState, useEffect, useMemo, useRef } from "react";
import type {
  Player,
  PlayerStats,
  PlayerStatsInput,
  PlayerStatNumericField,
  ResolvedPlayer,
} from "../types/types";
import { CATEGORIES, POSITIONS } from "../statCategories";
import { accentFor } from "../teamColors";

const API = "http://127.0.0.1:8000";

interface PlayerStatsTableProps {
  gameId: string;
  seasonId: string;
  teamId: string;
  opponentId: string;
  isHome: boolean;
}

function blankLine(
  gameId: string,
  playerId: string,
  teamId: string,
  opponentId: string,
  isHome: boolean,
): PlayerStatsInput {
  return { gameId, playerId, teamId, opponentId, isHome };
}

export default function PlayerStatsTable({
  gameId,
  seasonId,
  teamId,
  opponentId,
  isHome,
}: PlayerStatsTableProps) {
  const [category, setCategory] = useState(CATEGORIES[0].id);

  // The roster for this team in this season. This is the autocomplete
  // source — "who was on Indianapolis in season 4" is a roster question,
  // not a player question, because players change teams.
  const [roster, setRoster] = useState<Player[]>([]);

  // Stat lines keyed by player id, so a row can be looked up and updated
  // without scanning an array.
  const [lines, setLines] = useState<Record<string, PlayerStatsInput>>({});

  // Which rows have been edited since the last save. Saving every row on
  // every click would be 25 requests when one changed.
  const [dirty, setDirty] = useState<Set<string>>(new Set());

  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<Player[] | null>(null);

  // The category suggests a position for a new player, but it is only a
  // suggestion — a fullback added from the rushing table is not an HB.
  const [newPosition, setNewPosition] = useState(
    CATEGORIES[0].positions[0] ?? "QB",
  );

  const searchRef = useRef<HTMLInputElement>(null);
  const active = CATEGORIES.find((c) => c.id === category) ?? CATEGORIES[0];

  // Switching category re-suggests a position, so adding a kicker from the
  // kicking table does not inherit whatever was last picked.
  useEffect(() => {
    setNewPosition(active.positions[0] ?? "QB");
  }, [active]);

  // Roster and existing stat lines, loaded together.
  useEffect(() => {
    setLoading(true);
    setError(null);

    Promise.all([
      fetch(`${API}/players?teamId=${teamId}&seasonId=${seasonId}`).then((r) =>
        r.json(),
      ),
      fetch(`${API}/stats/players?gameId=${gameId}&teamId=${teamId}`).then(
        (r) => r.json(),
      ),
    ])
      .then(([players, stats]: [Player[], PlayerStats[]]) => {
        setRoster(players);
        const byPlayer: Record<string, PlayerStatsInput> = {};
        for (const line of stats) byPlayer[line.playerId] = line;
        setLines(byPlayer);
        setDirty(new Set());
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [gameId, seasonId, teamId]);

  // Rows shown in the current category: anyone who already has a line,
  // plus roster players whose position belongs to this category. Sorted so
  // players with numbers come first — the ones you are working on stay at
  // the top.
  const rows = useMemo(() => {
    const shown = new Map<string, Player>();
    for (const player of roster) {
      const hasLine = player.id in lines;
      const fits = active.positions.includes(player.position);
      if (hasLine || fits) shown.set(player.id, player);
    }
    return [...shown.values()].sort((a, b) => {
      const aHas = a.id in lines ? 0 : 1;
      const bHas = b.id in lines ? 0 : 1;
      return aHas - bHas || a.name.localeCompare(b.name);
    });
  }, [roster, lines, active]);

  const suggestions = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) return [];
    return roster
      .filter((p) => p.name.toLowerCase().includes(text))
      .filter((p) => !(p.id in lines))
      .slice(0, 8);
  }, [query, roster, lines]);

  function ensureLine(playerId: string): PlayerStatsInput {
    return (
      lines[playerId] ??
      blankLine(gameId, playerId, teamId, opponentId, isHome)
    );
  }

  function updateField(
    playerId: string,
    field: PlayerStatNumericField,
    raw: string,
  ) {
    const value = raw === "" ? 0 : Number(raw);
    if (Number.isNaN(value)) return;

    setLines((current) => ({
      ...current,
      [playerId]: { ...ensureLine(playerId), [field]: value },
    }));
    setDirty((current) => new Set(current).add(playerId));
  }

  function updateSacks(playerId: string, raw: string) {
    // Halves are real: two players sharing a sack get 0.5 each.
    if (raw !== "" && !/^\d+(\.[05])?$/.test(raw)) return;
    setLines((current) => ({
      ...current,
      [playerId]: { ...ensureLine(playerId), sacks: raw === "" ? "0" : raw },
    }));
    setDirty((current) => new Set(current).add(playerId));
  }

  function addPlayer(player: Player) {
    setLines((current) => ({
      ...current,
      [player.id]: blankLine(gameId, player.id, teamId, opponentId, isHome),
    }));
    if (!roster.some((p) => p.id === player.id)) {
      setRoster((current) => [...current, player]);
    }
    setQuery("");
    setCandidates(null);
    searchRef.current?.focus();
  }

  // Create a player who is not on the roster yet, or find one who is.
  // The API does both in one call and returns 409 with candidates when a
  // name is ambiguous, which is surfaced rather than guessed at.
  function resolveAndAdd(force = false, playerId?: string) {
    const name = query.trim();
    if (!name) return;

    setError(null);
    fetch(`${API}/players/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        position: newPosition,
        seasonId,
        teamId,
        forceNew: force,
        playerId,
      }),
    })
      .then(async (res) => {
        const body = await res.json().catch(() => null);
        if (res.status === 409) {
          setCandidates(body?.detail?.candidates ?? []);
          return null;
        }
        if (!res.ok) {
          throw new Error(
            typeof body?.detail === "string"
              ? body.detail
              : `HTTP ${res.status}`,
          );
        }
        return body as ResolvedPlayer;
      })
      .then((resolved) => {
        if (resolved) addPlayer(resolved.player);
      })
      .catch((err: Error) => setError(err.message));
  }

  function saveAll() {
    if (dirty.size === 0) return;
    setSaving(true);
    setError(null);

    const pending = [...dirty].map((playerId) =>
      fetch(`${API}/stats/players`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lines[playerId]),
      }).then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          const who = roster.find((p) => p.id === playerId)?.name ?? playerId;
          throw new Error(
            `${who}: ${typeof body?.detail === "string" ? body.detail : res.status}`,
          );
        }
        return res.json() as Promise<PlayerStats>;
      }),
    );

    Promise.all(pending)
      .then((saved) => {
        setLines((current) => {
          const next = { ...current };
          for (const line of saved) next[line.playerId] = line;
          return next;
        });
        setDirty(new Set());
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false));
  }

  if (loading) return <p className="loading">Loading</p>;

  return (
    <div
      className="player-stats"
      style={{ "--accent": accentFor(teamId) } as React.CSSProperties}
    >
      <div className="category-bar">
        {CATEGORIES.map((c) => (
          <button
            key={c.id}
            className={c.id === category ? "chip active" : "chip"}
            onClick={() => setCategory(c.id)}
          >
            {c.label}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}

      <table className="stat-table">
        <thead>
          <tr>
            <th className="player-col">Player</th>
            {active.id === "defense" && <th>Sacks</th>}
            {active.columns.map((col) => (
              <th key={col.field}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((player) => {
            const line = lines[player.id];
            return (
              <tr key={player.id} className={dirty.has(player.id) ? "dirty" : undefined}>
                <td className="player-col">
                  <span className="player-name">{player.name}</span>
                  <span className="player-pos">{player.position}</span>
                </td>
                {active.id === "defense" && (
                  <td>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={line?.sacks ?? "0"}
                      data-zero={(line?.sacks ?? "0") === "0"}
                      onChange={(e) => updateSacks(player.id, e.target.value)}
                    />
                  </td>
                )}
                {active.columns.map((col) => (
                  <td key={col.field}>
                    <input
                      type="number"
                      value={line?.[col.field] ?? 0}
                      data-zero={(line?.[col.field] ?? 0) === 0}
                      onChange={(e) =>
                        updateField(player.id, col.field, e.target.value)
                      }
                    />
                  </td>
                ))}
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td className="empty" colSpan={active.columns.length + 2}>
                No {active.label.toLowerCase()} players yet. Add one below.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="add-player">
        <input
          ref={searchRef}
          type="text"
          value={query}
          placeholder="Add a player by name"
          onChange={(e) => {
            setQuery(e.target.value);
            setCandidates(null);
          }}
          onKeyDown={(e) => {
            if (e.key !== "Enter") return;
            if (suggestions.length === 1) addPlayer(suggestions[0]);
            else if (suggestions.length === 0) resolveAndAdd();
          }}
        />

        {suggestions.length > 0 && (
          <ul className="suggestions">
            {suggestions.map((p) => (
              <li key={p.id}>
                <button onClick={() => addPlayer(p)}>
                  {p.name} <span className="player-pos">{p.position}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {query.trim() && suggestions.length === 0 && !candidates && (
          <div className="new-player">
            <select
              value={newPosition}
              onChange={(e) => setNewPosition(e.target.value)}
            >
              {POSITIONS.map((pos) => (
                <option key={pos} value={pos}>
                  {pos}
                </option>
              ))}
            </select>
            <button className="ghost" onClick={() => resolveAndAdd()}>
              Add {query.trim()}
            </button>
          </div>
        )}

        {candidates && (
          <div className="candidates">
            <p>More than one player is named {query.trim()}. Which one?</p>
            {candidates.map((p) => (
              <button key={p.id} onClick={() => resolveAndAdd(false, p.id)}>
                {p.name} <span className="player-pos">{p.position}</span>
              </button>
            ))}
            <button className="ghost" onClick={() => resolveAndAdd(true)}>
              None of these, create another
            </button>
          </div>
        )}
      </div>

      <div className="form-actions">
        <button
          className="save-button"
          onClick={saveAll}
          disabled={saving || dirty.size === 0}
        >
          {saving
            ? "Saving"
            : dirty.size === 0
              ? "Saved"
              : `Save ${dirty.size} ${dirty.size === 1 ? "line" : "lines"}`}
        </button>
      </div>
    </div>
  );
}