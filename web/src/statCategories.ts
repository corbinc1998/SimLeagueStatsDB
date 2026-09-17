import type { PlayerStatNumericField } from "./types/types";

// The box score is read one category at a time, so it is entered one
// category at a time. Each category is a table: players down the side,
// that category's columns across the top.
//
// `positions` is which roles default into this category — it seeds the
// table with the right players rather than making you add a quarterback
// to the passing table by hand every game.

export interface StatColumn {
  field: PlayerStatNumericField;
  label: string;
  width?: number;
}

export interface StatCategory {
  id: string;
  label: string;
  positions: string[];
  columns: StatColumn[];
}

export const CATEGORIES: StatCategory[] = [
  {
    id: "passing",
    label: "Passing",
    positions: ["QB"],
    columns: [
      { field: "passCompletions", label: "Comp" },
      { field: "passAttempts", label: "Att" },
      { field: "passYards", label: "Yds" },
      { field: "passTouchdowns", label: "TD" },
      { field: "interceptions", label: "Int" },
      { field: "passLong", label: "Lng" },
    ],
  },
  {
    id: "rushing",
    label: "Rushing",
    positions: ["RB", "HB", "FB", "QB"],
    columns: [
      { field: "rushAttempts", label: "Att" },
      { field: "rushYards", label: "Yds" },
      { field: "rushTouchdowns", label: "TD" },
      { field: "fumbles", label: "Fum" },
      { field: "brokenTackles", label: "BTk" },
      { field: "yardsAfterFirstHit", label: "1stH" },
      { field: "rushes20Plus", label: "20+" },
      { field: "rushLong", label: "Lng" },
    ],
  },
  {
    id: "receiving",
    label: "Receiving",
    positions: ["WR", "TE", "RB", "HB", "FB"],
    columns: [
      { field: "receptions", label: "Rec" },
      { field: "receivingYards", label: "Yds" },
      { field: "receivingTouchdowns", label: "TD" },
      { field: "yardsAfterCatch", label: "YAC" },
      { field: "drops", label: "Drp" },
      { field: "receptionLong", label: "Lng" },
    ],
  },
  {
    id: "blocking",
    label: "Blocking",
    positions: ["LT", "LG", "C", "RG", "RT", "OL", "TE"],
    columns: [
      { field: "pancakes", label: "Pancake" },
      { field: "sacksAllowed", label: "Sacks Allowed" },
    ],
  },
  {
    id: "defense",
    label: "Defense",
    positions: ["DE", "DT", "LE", "RE", "LOLB", "MLB", "ROLB", "LB", "CB", "FS", "SS", "S"],
    columns: [
      { field: "soloTackles", label: "Solo" },
      { field: "assistedTackles", label: "Ast" },
      { field: "tacklesForLoss", label: "TFL" },
      { field: "interceptionsMade", label: "Int" },
      { field: "interceptionYards", label: "IYds" },
      { field: "interceptionLong", label: "ILng" },
      { field: "passesDefended", label: "PD" },
      { field: "forcedFumbles", label: "FF" },
      { field: "fumblesRecovered", label: "FR" },
      { field: "fumbleReturnYards", label: "FYds" },
      { field: "blockedKicks", label: "Blk" },
      { field: "safeties", label: "Sfty" },
      { field: "defensiveTouchdowns", label: "TD" },
    ],
  },
  {
    id: "kicking",
    label: "Kicking",
    positions: ["K"],
    columns: [
      { field: "fieldGoalsMade", label: "FGM" },
      { field: "fieldGoalsAttempted", label: "FGA" },
      { field: "fieldGoalLong", label: "Lng" },
      { field: "fieldGoalsBlocked", label: "Blk" },
      { field: "extraPointsMade", label: "XPM" },
      { field: "extraPointsAttempted", label: "XPA" },
      { field: "extraPointsBlocked", label: "XPBlk" },
      { field: "fgm29", label: "M/29" },
      { field: "fga29", label: "A/29" },
      { field: "fgm39", label: "M/39" },
      { field: "fga39", label: "A/39" },
      { field: "fgm49", label: "M/49" },
      { field: "fga49", label: "A/49" },
      { field: "fgm50Plus", label: "M/50+" },
      { field: "fga50Plus", label: "A/50+" },
      { field: "kickoffs", label: "KO" },
      { field: "touchbacks", label: "TB" },
    ],
  },
  {
    id: "punting",
    label: "Punting",
    positions: ["P"],
    columns: [
      { field: "punts", label: "Punts" },
      { field: "puntYards", label: "Yds" },
      { field: "puntNetYards", label: "Net" },
      { field: "puntsBlocked", label: "Blk" },
      { field: "puntsInside20", label: "In20" },
      { field: "puntTouchbacks", label: "TB" },
      { field: "puntLong", label: "Lng" },
    ],
  },
  {
    id: "returns",
    label: "Returns",
    positions: ["WR", "RB", "HB", "CB"],
    columns: [
      { field: "kickReturns", label: "KR" },
      { field: "kickReturnYards", label: "KR Yds" },
      { field: "kickReturnLong", label: "KR Lng" },
      { field: "kickReturnTouchdowns", label: "KR TD" },
      { field: "puntReturns", label: "PR" },
      { field: "puntReturnYards", label: "PR Yds" },
      { field: "puntReturnLong", label: "PR Lng" },
      { field: "puntReturnTouchdowns", label: "PR TD" },
    ],
  },
];

// sacks is the one stat that is not an integer — halves are real when two
// players share one — so it is entered separately rather than in the
// defense grid with everything else.
export const SACKS_FIELD = "sacks" as const;