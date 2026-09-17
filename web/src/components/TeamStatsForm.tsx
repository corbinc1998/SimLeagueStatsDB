import { useState, useEffect } from "react";
import type { TeamStats, TeamStatsInput } from "../types/types";
import { accentFor } from "../teamColors";

const API = "http://127.0.0.1:8000";

interface TeamStatsFormProps {
  gameId: string;
  teamId: string;
  opponentId: string;
  isHome: boolean;
  /** From the game record. Prefilled so the score is never retyped. */
  points: number;
}

// The order here is the order the box score shows them, top to bottom.
// That is the whole point: you read down the screen and type down the
// form without hunting for the next field.
type SimpleField =
  | "totalOffense"
  | "rushYards"
  | "passYards"
  | "firstDowns"
  | "puntReturnYards"
  | "kickReturnYards"
  | "totalYards"
  | "turnovers";

const SIMPLE_FIELDS: { field: SimpleField; label: string }[] = [
  { field: "totalOffense", label: "Total Offense" },
  { field: "rushYards", label: "Rushing Yards" },
  { field: "passYards", label: "Passing Yards" },
  { field: "firstDowns", label: "First Downs" },
  { field: "puntReturnYards", label: "PR Yards" },
  { field: "kickReturnYards", label: "KR Yards" },
  { field: "totalYards", label: "Total Yards" },
  { field: "turnovers", label: "Turnovers" },
];

// Several stats appear on screen as one string holding two numbers. They
// are typed the way they are displayed and split on the way to the
// database, where two integers can be summed and averaged and a string
// like "4-16" cannot.
function parsePair(raw: string): [number, number] | null {
  const match = raw.match(/^(\d+)\s*-\s*(\d+)$/);
  if (!match) return null;
  return [Number(match[1]), Number(match[2])];
}

function formatPair(a: number, b: number): string {
  return `${a}-${b}`;
}

function parseClock(raw: string): number | null {
  const match = raw.match(/^(\d{1,2}):([0-5]\d)$/);
  if (!match) return null;
  return Number(match[1]) * 60 + Number(match[2]);
}

function formatClock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function blankStats(
  gameId: string,
  teamId: string,
  opponentId: string,
  isHome: boolean,
  points: number,
): TeamStatsInput {
  return {
    gameId,
    teamId,
    opponentId,
    isHome,
    points,
    totalOffense: 0,
    rushYards: 0,
    passYards: 0,
    firstDowns: 0,
    puntReturnYards: 0,
    kickReturnYards: 0,
    totalYards: 0,
    turnovers: 0,
    thirdDownConv: 0,
    thirdDownAtt: 0,
    fourthDownConv: 0,
    fourthDownAtt: 0,
    twoPointConversionsMade: 0,
    twoPointConversionsAttempted: 0,
    redzoneTrips: 0,
    redzoneTouchdowns: 0,
    redzoneFieldGoals: 0,
    penalties: 0,
    penaltyYards: 0,
    timeOfPossession: 0,
  };
}

export default function TeamStatsForm({
  gameId,
  teamId,
  opponentId,
  isHome,
  points,
}: TeamStatsFormProps) {
  const [form, setForm] = useState<TeamStatsInput>(
    blankStats(gameId, teamId, opponentId, isHome, points),
  );

  // Composite fields keep their own text state so you can type "4-1"
  // on the way to "4-16" without the parse rejecting each keystroke.
  const [thirdDown, setThirdDown] = useState("0-0");
  const [fourthDown, setFourthDown] = useState("0-0");
  const [twoPoint, setTwoPoint] = useState("0-0");
  const [redzone, setRedzone] = useState("0-0");
  const [penalties, setPenalties] = useState("0-0");
  const [clock, setClock] = useState("0:00");
  const [invalid, setInvalid] = useState<Set<string>>(new Set());

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exists, setExists] = useState(false);

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
        const next =
          data ?? blankStats(gameId, teamId, opponentId, isHome, points);
        setForm(next);
        setThirdDown(
          formatPair(next.thirdDownConv ?? 0, next.thirdDownAtt ?? 0),
        );
        setFourthDown(
          formatPair(next.fourthDownConv ?? 0, next.fourthDownAtt ?? 0),
        );
        setTwoPoint(
          formatPair(
            next.twoPointConversionsMade ?? 0,
            next.twoPointConversionsAttempted ?? 0,
          ),
        );
        setRedzone(
          formatPair(
            (next.redzoneTouchdowns ?? 0) + (next.redzoneFieldGoals ?? 0),
            next.redzoneTrips ?? 0,
          ),
        );
        setPenalties(formatPair(next.penalties ?? 0, next.penaltyYards ?? 0));
        setClock(formatClock(next.timeOfPossession ?? 0));
        setExists(data !== null);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [gameId, teamId, opponentId, isHome, points]);

  function markInvalid(key: string, bad: boolean) {
    setInvalid((current) => {
      const next = new Set(current);
      if (bad) next.add(key);
      else next.delete(key);
      return next;
    });
  }

  function updateField(field: keyof TeamStatsInput, raw: string) {
    const value = raw === "" ? 0 : Number(raw);
    if (Number.isNaN(value)) return;
    setForm((current) => ({ ...current, [field]: value }));
  }

  // One handler for every "x-y" field. The two target columns differ, so
  // they are passed in rather than derived.
  function updatePair(
    key: string,
    raw: string,
    setText: (value: string) => void,
    first: keyof TeamStatsInput,
    second: keyof TeamStatsInput,
  ) {
    setText(raw);
    const parsed = parsePair(raw);
    markInvalid(key, parsed === null);
    if (parsed) {
      setForm((current) => ({
        ...current,
        [first]: parsed[0],
        [second]: parsed[1],
      }));
    }
  }

  // Red zone shows as scores-trips. The numerator is the sum of red zone
  // touchdowns and field goals, which are entered separately below, so
  // only the trips are stored from here — the numerator is checked
  // against those two instead.
  function updateRedzone(raw: string) {
    setRedzone(raw);
    const parsed = parsePair(raw);
    markInvalid("redzone", parsed === null);
    if (parsed) {
      setForm((current) => ({ ...current, redzoneTrips: parsed[1] }));
    }
  }

  function updateClock(raw: string) {
    setClock(raw);
    const seconds = parseClock(raw);
    markInvalid("clock", seconds === null);
    if (seconds !== null) {
      setForm((current) => ({ ...current, timeOfPossession: seconds }));
    }
  }

  const redzoneParsed = parsePair(redzone);
  const redzoneScores =
    (form.redzoneTouchdowns ?? 0) + (form.redzoneFieldGoals ?? 0);
  const redzoneMismatch =
    redzoneParsed !== null && redzoneParsed[0] !== redzoneScores;

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
        setExists(true);
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setSaving(false));
  }

  if (loading) return <p className="loading">Loading</p>;

  return (
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

      <div className="stat-list">
        <Row label="Score">
          <input
            type="number"
            value={form.points}
            onFocus={(e) => e.target.select()}
            onChange={(e) => updateField("points", e.target.value)}
          />
        </Row>

        {SIMPLE_FIELDS.map(({ field, label }) => (
          <Row key={field} label={label}>
            <input
              type="number"
              value={form[field] ?? 0}
              data-zero={(form[field] ?? 0) === 0}
              onFocus={(e) => e.target.select()}
              onChange={(e) => updateField(field, e.target.value)}
            />
          </Row>
        ))}

        <Row label="3rd Down Conv" hint="4-16">
          <PairInput
            value={thirdDown}
            invalid={invalid.has("third")}
            onChange={(raw) =>
              updatePair(
                "third",
                raw,
                setThirdDown,
                "thirdDownConv",
                "thirdDownAtt",
              )
            }
          />
        </Row>

        <Row label="4th Down Conv" hint="1-2">
          <PairInput
            value={fourthDown}
            invalid={invalid.has("fourth")}
            onChange={(raw) =>
              updatePair(
                "fourth",
                raw,
                setFourthDown,
                "fourthDownConv",
                "fourthDownAtt",
              )
            }
          />
        </Row>

        <Row label="2 Point Conv" hint="0-1">
          <PairInput
            value={twoPoint}
            invalid={invalid.has("twoPoint")}
            onChange={(raw) =>
              updatePair(
                "twoPoint",
                raw,
                setTwoPoint,
                "twoPointConversionsMade",
                "twoPointConversionsAttempted",
              )
            }
          />
        </Row>

        <Row label="Red Zone" hint="2-2">
          <PairInput
            value={redzone}
            invalid={invalid.has("redzone")}
            onChange={updateRedzone}
          />
        </Row>

        <Row label="Red Zone TD">
          <input
            type="number"
            value={form.redzoneTouchdowns ?? 0}
            data-zero={(form.redzoneTouchdowns ?? 0) === 0}
            onFocus={(e) => e.target.select()}
            onChange={(e) => updateField("redzoneTouchdowns", e.target.value)}
          />
        </Row>

        <Row label="Red Zone FG">
          <input
            type="number"
            value={form.redzoneFieldGoals ?? 0}
            data-zero={(form.redzoneFieldGoals ?? 0) === 0}
            onFocus={(e) => e.target.select()}
            onChange={(e) => updateField("redzoneFieldGoals", e.target.value)}
          />
        </Row>

        <Row label="Penalties" hint="2-15">
          <PairInput
            value={penalties}
            invalid={invalid.has("penalties")}
            onChange={(raw) =>
              updatePair(
                "penalties",
                raw,
                setPenalties,
                "penalties",
                "penaltyYards",
              )
            }
          />
        </Row>

        <Row label="Possession" hint="17:15">
          <input
            type="text"
            inputMode="numeric"
            value={clock}
            className={invalid.has("clock") ? "invalid" : undefined}
            onFocus={(e) => e.target.select()}
            onChange={(e) => updateClock(e.target.value)}
          />
        </Row>
      </div>

      {redzoneMismatch && (
        <p className="warn">
          Red zone shows {redzoneParsed?.[0]} scores, but TD + FG is{" "}
          {redzoneScores}.
        </p>
      )}

      <div className="form-actions">
        <button
          className="save-button"
          onClick={save}
          disabled={saving || invalid.size > 0}
        >
          {saving ? "Saving" : exists ? "Update" : "Save"}
        </button>
        {invalid.size > 0 && (
          <span className="error">Check the highlighted fields</span>
        )}
      </div>
    </div>
  );
}

function Row({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="stat-row">
      <span className="stat-label">
        {label}
        {hint && <span className="stat-hint">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

function PairInput({
  value,
  invalid,
  onChange,
}: {
  value: string;
  invalid: boolean;
  onChange: (raw: string) => void;
}) {
  return (
    <input
      type="text"
      inputMode="numeric"
      value={value}
      className={invalid ? "invalid" : undefined}
      onFocus={(e) => e.target.select()}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}