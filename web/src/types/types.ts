// Shared types, mirroring what the API returns.
//
// The API speaks camelCase (Pydantic's alias_generator handles the
// translation to snake_case columns on the Python side), so these match
// the JSON exactly.

export interface Game {
    id: string;
    seasonId: string;
    week: number;
    homeTeamId: string;
    awayTeamId: string;
    homeScore: number;
    awayScore: number;
    date: string;
    completed: boolean;
    isPlayoff: boolean;
    round: string | null;
    conference: string | null;
    matchup: number | null;
    homeTeamSeed: string | null;
    awayTeamSeed: string | null;
  }
  
  export interface Season {
    id: string;
    leagueId: string;
    name: string;
  }
  
  export interface Team {
    id: string;
    name: string;
    conference: string | null;
    division: string | null;
  }
  
  export interface Player {
    id: string;
    name: string;
    position: string;
  }
  
  // The four fields that identify which team in which game. Everything else
  // on a stat line is a number with a database default of 0.
  interface StatLineIdentity {
    gameId: string;
    teamId: string;
    opponentId: string;
    isHome: boolean;
  }
  
  // What comes back from the API: every field present, because the database
  // fills the defaults.
  export interface TeamStats extends StatLineIdentity {
    points: number;
  
    firstDowns: number;
    thirdDownAtt: number;
    thirdDownConv: number;
    fourthDownAtt: number;
    fourthDownConv: number;
  
    totalYards: number;
    totalOffense: number;
    passYards: number;
    passAttempts: number;
    passCompletions: number;
    rushYards: number;
    rushAttempts: number;
  
    kickReturnYards: number;
    puntReturnYards: number;
  
    sacksAllowed: number;
    sackYardsLost: number;
  
    turnovers: number;
    interceptionsLost: number;
    fumblesLost: number;
  
    penalties: number;
    penaltyYards: number;
  
    twoPointConversionsMade: number;
    twoPointConversionsAttempted: number;
  
    redzoneTrips: number;
    redzoneTouchdowns: number;
    redzoneFieldGoals: number;
  
    timeOfPossession: number;
  }
  
  // What you send to create one. The identity fields and points are
  // required; every other stat can be omitted and the database default of 0
  // applies.
  //
  // Partial<T> makes every field of T optional. Omit<T, K> removes fields.
  // Combined: take TeamStats, drop the identity fields and points, make the
  // rest optional, then add the required ones back.
  export type TeamStatsInput = StatLineIdentity & {
    points: number;
  } & Partial<Omit<TeamStats, keyof StatLineIdentity | "points">>;