import { useState, useEffect } from "react";
import type { TeamStats, TeamStatsInput } from "../types/types";
import { accentFor } from "../teamColors";

const API = "http://127.0.0.1:8000";

interface TeamStatsFormProps {
  gameId: string;
  teamId: string;
  opponentId: string;
  isHome: boolean;
}

// Every stat field on the model, grouped the way the box score screen
// groups them. Defining these as data rather than as 28 hand-written
// inputs means adding a field later is one line, and the form cannot
// drift out of sync with itself.
//
// `as const` makes TypeScript treat the field names as literal strings
// rather than plain `string`, which is what lets them be checked against
// keyof TeamStatsInput.
const SECTIONS = [
  {
    title: "Scoring",
    fields: [
      { field: "points", label: "Points" },
      { field: "firstDowns", label: "First Downs" },
    ],
  },
  {
    title: "Offense",
    fields: [
      { field: "totalOffense", label: "Total Offense" },
      { field: "totalYards", label: "Total Yards" },
      { field: "passYards", label: "Pass Yards" },
      { field: "passAttempts", label: "Pass Att" },
      { field: "passCompletions", label: "Pass Comp" },
      { field: "rushYards", label: "Rush Yards" },
      { field: "rushAttempts", label: "Rush Att" },
    ],
  },
  {
    title: "Conversions",
    fields: [
      { field: "thirdDownConv", label: "3rd Down Conv" },
      { field: "thirdDownAtt", label: "3rd Down Att" },
      { field: "fourthDownConv", label: "4th Down Conv" },
      { field: "fourthDownAtt", label: "4th Down Att" },
      { field: "twoPointConversionsMade", label: "2pt Made" },
      { field: "twoPointConversionsAttempted", label: "2pt Att" },
    ],
  },
  {
    title: "Red Zone",
    fields: [
      { field: "redzoneTrips", label: "RZ Trips" },
      { field: "redzoneTouchdowns", label: "RZ TD" },
      { field: "redzoneFieldGoals", label: "RZ FG" },
    ],
  },
  {
    title: "Returns",
    fields: [
      { field: "kickReturnYards", label: "KR Yards" },
      { field: "puntReturnYards", label: "PR Yards" },
    ],
  },
  {
    title: "Giveaways",
    fields: [
      { field: "turnovers", label: "Turnovers" },
      { field: "interceptionsLost", label: "INT Lost" },
      { field: "fumblesLost", label: "Fumbles Lost" },
      { field: "sacksAllowed", label: "Sacks Allowed" },
      { field: "sackYardsLost", label: "Sack Yds Lost" },
    ],
  },
  {
    title: "Penalties",
    fields: [
      { field: "penalties", label: "Penalties" },
      { field: "penaltyYards", label: "Penalty Yards" },
    ],
  },
] as const satisfies ReadonlyArray<{
  title: string;
  fields: ReadonlyArray<{ field: keyof TeamStatsInput; label: string }>;
}>;

// The box score shows possession as 17:15, the column stores seconds.
// Converting at the edge keeps the stored value summable and sortable —
// a string like "17:15" cannot be averaged.
function secondsToClock(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${String(secs).padStart(2, "0")}`;
}

function clockToSeconds(clock: string): number | null {
  const match = clock.match(/^(\d{1,2}):([0-5]\d)$/);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

function blankStats(
  gameId: string,
  teamId: string,
  opponentId: string,
  isHome: boolean,
): TeamStatsInput {
  // Zero every stat field from the same definition the inputs use, so the
  // two cannot disagree. Built as a plain record first, because assigning
  // by a computed key needs an index signature that TeamStatsInput does
  // not have.
  const zeroed: Record<string, number> = { timeOfPossession: 0 };
  for (const section of SECTIONS) {
    for (const { field } of section.fields) {
      zeroed[field] = 0;
    }
  }

  return {
    gameId,
    teamId,
    opponentId,
    isHome,
    ...zeroed,
    points: zeroed.points ?? 0,
  };
}

export default function TeamStatsForm({
  gameId,
  teamId,
  opponentId,
  isHome,
}: TeamStatsFormProps) {
  const [form, setForm] = useState<TeamStatsInput>(
    blankStats(gameId, teamId, opponentId, isHome),
  );
  const [clock, setClock] = useState("0:00");
  const [clockValid, setClockValid] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exists, setExists] = useState(false);

  // Load whatever is stored for this team in this game. A 404 means
  // nothing has been entered yet, which is the normal case on a fresh
  // game, so the blank form stands.
  useEffect(() => {
    setLoading(true);
    setError(null);

    fetch(`${API}/stats/teams/${gameId}/${teamId}`)
      .then((res) => {
        if (res.status === 404) return null;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data: TeamStats | null) => {
        const next = data ?? blankStats(gameId, teamId, opponentId, isHome);
        setForm(next);
        setClock(secondsToClock(next.timeOfPossession ?? 0));
        setExists(data !== null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [gameId, teamId, opponentId, isHome]);

  // One handler for every numeric input. The spread is the important
  // part: state is replaced, never mutated. Writing form[field] = value
  // would change the object React already holds, so React would see no
  // change and skip the re-render.
  function updateField(field: keyof TeamStatsInput, raw: string) {
    const value = raw === "" ? 0 : Number(raw);
    if (Number.isNaN(value)) return;
    setForm((current) => ({ ...current, [field]: value }));
  }

  function updateClock(raw: string) {
    setClock(raw);
    const seconds = clockToSeconds(raw);
    setClockValid(seconds !== null);
    if (seconds !== null) {
      setForm((current) => ({ ...current, timeOfPossession: seconds }));
    }
  }

  function save() {
    setSaving(true);
    setError(null);

    fetch(`${API}/stats/teams`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    })
      .then(async (res) => {
        if (!res.ok) {
          const body = await res.json().catch(() => null);
          throw new Error(
            typeof body?.detail === "string"
              ? body.detail
              : `HTTP ${res.status}`,
          );
        }
        return res.json();
      })
      .then((data: TeamStats) => {
        setForm(data);
        setClock(secondsToClock(data.timeOfPossession));
        setExists(true);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false));
  }

  if (loading) return <p className="loading">Loading</p>;

  return (
    // The team's colour is injected as a custom property rather than a
    // class, because it comes from data. Everything inside the column
    // reads --accent: the spine, the focus underline, the save button.
    <div
      className="team-stats-form"
      style={{ "--accent": accentFor(teamId) } as React.CSSProperties}
    >
      <div className="form-head">
        <img alt={teamId} className="logo" src={`/logos/${teamId}.png`} />
        <h3>{teamId.toUpperCase()}</h3>
        <span className="side-label">{isHome ? "home" : "away"}</span>
        {exists && <span className="saved-badge">saved</span>}
      </div>

      {error && <p className="error">{error}</p>}

      {SECTIONS.map((section) => (
        <fieldset key={section.title}>
          <legend>{section.title}</legend>
          <div className="stat-grid">
            {section.fields.map(({ field, label }) => (
              <StatInput
                key={field}
                label={label}
                field={field}
                value={form[field] as number | undefined}
                onChange={updateField}
              />
            ))}
          </div>
        </fieldset>
      ))}

      <fieldset>
        <legend>Possession</legend>
        <div className="stat-grid">
          <label className="stat-input">
            <span>Time of Possession</span>
            <input
              type="text"
              value={clock}
              placeholder="17:15"
              onChange={(e) => updateClock(e.target.value)}
              className={clockValid ? undefined : "invalid"}
            />
          </label>
        </div>
      </fieldset>

      <div className="form-actions">
        <button
          className="save-button"
          onClick={save}
          disabled={saving || !clockValid}
        >
          {saving ? "Saving" : exists ? "Update" : "Save"}
        </button>
        {!clockValid && <span className="error">Possession needs MM:SS</span>}
      </div>
    </div>
  );
}

interface StatInputProps {
  label: string;
  field: keyof TeamStatsInput;
  value: number | undefined;
  onChange: (field: keyof TeamStatsInput, raw: string) => void;
}

function StatInput({ label, field, value, onChange }: StatInputProps) {
  return (
    <label className="stat-input">
      <span>{label}</span>
      <input
        type="number"
        name={field}
        value={value ?? 0}
        data-zero={(value ?? 0) === 0}
        onChange={(e) => onChange(field, e.target.value)}
      />
    </label>
  );
}