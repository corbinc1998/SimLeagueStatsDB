-- 001_initial.sql
--
-- SimLeague schema.
--
-- Conventions:
--   snake_case columns (Postgres convention; the API speaks camelCase and
--   translates at the Pydantic boundary via alias_generator)
--   natural composite primary keys on the stat tables, so "one row per
--   player per game" is enforced by the database rather than by a check in
--   application code
--   opponent_id and is_home denormalized onto both stat tables, because
--   "vs a certain team" is the primary access pattern

BEGIN;

-- ---------------------------------------------------------------- core

CREATE TABLE leagues (
    id   text PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE seasons (
    id        text PRIMARY KEY,
    league_id text NOT NULL REFERENCES leagues (id) ON DELETE CASCADE,
    name      text NOT NULL
);

CREATE TABLE teams (
    id         text PRIMARY KEY,
    name       text NOT NULL,
    conference text CHECK (conference IN ('AFC', 'NFC')),
    division   text CHECK (division IN ('East', 'North', 'South', 'West'))
);

CREATE TABLE players (
    id       text PRIMARY KEY,
    name     text NOT NULL,
    position text NOT NULL
);

-- Roster membership per season. A player's team is not a property of the
-- player, because it changes: drafted, traded, released, retired. The
-- authoritative team for any given stat line is the team_id on that row;
-- this table is the roster snapshot for display and for "who was on the
-- 2007 Colts" questions.
CREATE TABLE player_seasons (
    player_id     text NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    season_id     text NOT NULL REFERENCES seasons (id) ON DELETE CASCADE,
    team_id       text NOT NULL REFERENCES teams (id),
    position      text,
    jersey_number smallint,
    PRIMARY KEY (player_id, season_id)
);

-- ---------------------------------------------------------------- games

CREATE TABLE games (
    id             text PRIMARY KEY,
    season_id      text NOT NULL REFERENCES seasons (id) ON DELETE CASCADE,
    week           smallint NOT NULL CHECK (week > 0),
    home_team_id   text NOT NULL REFERENCES teams (id),
    away_team_id   text NOT NULL REFERENCES teams (id),
    home_score     smallint NOT NULL CHECK (home_score >= 0),
    away_score     smallint NOT NULL CHECK (away_score >= 0),
    played_at      timestamptz NOT NULL,
    completed      boolean NOT NULL DEFAULT false,

    is_playoff     boolean NOT NULL DEFAULT false,
    round          text CHECK (
                       round IN ('wildcard', 'divisional', 'conference', 'superbowl')
                   ),
    conference     text CHECK (conference IN ('AFC', 'NFC')),
    matchup        smallint,
    home_team_seed smallint,
    away_team_seed smallint,

    CONSTRAINT game_teams_differ CHECK (home_team_id <> away_team_id),
    CONSTRAINT playoff_fields_only_on_playoffs CHECK (
        is_playoff OR (
            round IS NULL
            AND matchup IS NULL
            AND home_team_seed IS NULL
            AND away_team_seed IS NULL
        )
    ),
    -- A Super Bowl is not a conference game.
    CONSTRAINT superbowl_has_no_conference CHECK (
        round IS DISTINCT FROM 'superbowl' OR conference IS NULL
    )
);

CREATE INDEX games_season_week_idx ON games (season_id, week);
CREATE INDEX games_home_team_idx   ON games (home_team_id);
CREATE INDEX games_away_team_idx   ON games (away_team_id);
CREATE INDEX games_played_at_idx   ON games (played_at);

-- timestamptz, not timestamp. The export mixes naive and Z-suffixed values;
-- normalizing to UTC at the boundary means the column never holds an
-- ambiguous local time.

-- ------------------------------------------------------- team box scores

-- One row per team per game, so exactly two rows per game. The composite
-- primary key is what makes that structural.
--
-- Entered from the box score rather than summed from player rows: team
-- passing yards net out sack yardage, so the two will not agree and one of
-- them has to be authoritative. This table is it.
CREATE TABLE team_game_stats (
    game_id     text NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    team_id     text NOT NULL REFERENCES teams (id),
    opponent_id text NOT NULL REFERENCES teams (id),
    is_home     boolean NOT NULL,

    points      smallint NOT NULL CHECK (points >= 0),

    first_downs        smallint NOT NULL DEFAULT 0,
    third_down_att     smallint NOT NULL DEFAULT 0,
    third_down_conv    smallint NOT NULL DEFAULT 0,
    fourth_down_att    smallint NOT NULL DEFAULT 0,
    fourth_down_conv   smallint NOT NULL DEFAULT 0,

    total_yards        smallint NOT NULL DEFAULT 0,
    pass_yards         smallint NOT NULL DEFAULT 0,
    pass_attempts      smallint NOT NULL DEFAULT 0,
    pass_completions   smallint NOT NULL DEFAULT 0,
    rush_yards         smallint NOT NULL DEFAULT 0,
    rush_attempts      smallint NOT NULL DEFAULT 0,

    sacks_allowed      smallint NOT NULL DEFAULT 0,
    sack_yards_lost    smallint NOT NULL DEFAULT 0,

    turnovers          smallint NOT NULL DEFAULT 0,
    interceptions_lost smallint NOT NULL DEFAULT 0,
    fumbles_lost       smallint NOT NULL DEFAULT 0,

    penalties          smallint NOT NULL DEFAULT 0,
    penalty_yards      smallint NOT NULL DEFAULT 0,

    -- Seconds. Simpler to sum and average than an interval, and the
    -- display formatting belongs in the API layer anyway.
    time_of_possession integer NOT NULL DEFAULT 0
        CHECK (time_of_possession BETWEEN 0 AND 5400),

    PRIMARY KEY (game_id, team_id),
    CONSTRAINT team_game_opponent_differs CHECK (team_id <> opponent_id),
    CONSTRAINT third_downs_sane  CHECK (third_down_conv <= third_down_att),
    CONSTRAINT fourth_downs_sane CHECK (fourth_down_conv <= fourth_down_att),
    CONSTRAINT completions_sane  CHECK (pass_completions <= pass_attempts)
);

CREATE INDEX team_game_stats_team_idx     ON team_game_stats (team_id);
CREATE INDEX team_game_stats_opponent_idx ON team_game_stats (opponent_id);

-- The splits index. "How does Indianapolis play against Jacksonville" is
-- a single index scan rather than a join through games.
CREATE INDEX team_game_stats_matchup_idx
    ON team_game_stats (team_id, opponent_id);

-- ----------------------------------------------------- player box scores

-- One row per player per game. The composite primary key enforces that,
-- which closes the duplicate-stat-line gap structurally.
--
-- team_id is on the row rather than looked up from the player, because
-- players change teams. This is what keeps historical totals correct after
-- a trade.
CREATE TABLE player_game_stats (
    game_id     text NOT NULL REFERENCES games (id) ON DELETE CASCADE,
    player_id   text NOT NULL REFERENCES players (id) ON DELETE CASCADE,
    team_id     text NOT NULL REFERENCES teams (id),
    opponent_id text NOT NULL REFERENCES teams (id),
    is_home     boolean NOT NULL,

    -- passing
    pass_attempts      smallint NOT NULL DEFAULT 0,
    pass_completions   smallint NOT NULL DEFAULT 0,
    pass_yards         smallint NOT NULL DEFAULT 0,
    pass_touchdowns    smallint NOT NULL DEFAULT 0,
    interceptions      smallint NOT NULL DEFAULT 0,
    sacks_taken        smallint NOT NULL DEFAULT 0,

    -- rushing
    rush_attempts      smallint NOT NULL DEFAULT 0,
    rush_yards         smallint NOT NULL DEFAULT 0,
    rush_touchdowns    smallint NOT NULL DEFAULT 0,
    fumbles            smallint NOT NULL DEFAULT 0,
    fumbles_lost       smallint NOT NULL DEFAULT 0,

    -- receiving
    targets            smallint NOT NULL DEFAULT 0,
    receptions         smallint NOT NULL DEFAULT 0,
    receiving_yards    smallint NOT NULL DEFAULT 0,
    receiving_touchdowns smallint NOT NULL DEFAULT 0,

    -- defense
    tackles            smallint NOT NULL DEFAULT 0,
    tackles_for_loss   smallint NOT NULL DEFAULT 0,
    sacks              numeric(4, 1) NOT NULL DEFAULT 0,
    interceptions_made smallint NOT NULL DEFAULT 0,
    passes_defended    smallint NOT NULL DEFAULT 0,
    forced_fumbles     smallint NOT NULL DEFAULT 0,
    fumbles_recovered  smallint NOT NULL DEFAULT 0,
    defensive_touchdowns smallint NOT NULL DEFAULT 0,

    -- kicking
    field_goals_made     smallint NOT NULL DEFAULT 0,
    field_goals_attempted smallint NOT NULL DEFAULT 0,
    extra_points_made    smallint NOT NULL DEFAULT 0,
    extra_points_attempted smallint NOT NULL DEFAULT 0,
    punts                smallint NOT NULL DEFAULT 0,
    punt_yards           smallint NOT NULL DEFAULT 0,

    -- returns
    kick_returns         smallint NOT NULL DEFAULT 0,
    kick_return_yards    smallint NOT NULL DEFAULT 0,
    punt_returns         smallint NOT NULL DEFAULT 0,
    punt_return_yards    smallint NOT NULL DEFAULT 0,
    return_touchdowns    smallint NOT NULL DEFAULT 0,

    PRIMARY KEY (game_id, player_id),
    CONSTRAINT player_game_opponent_differs CHECK (team_id <> opponent_id),
    CONSTRAINT player_completions_sane CHECK (pass_completions <= pass_attempts),
    CONSTRAINT player_receptions_sane  CHECK (receptions <= targets OR targets = 0),
    CONSTRAINT player_fumbles_sane     CHECK (fumbles_lost <= fumbles),
    CONSTRAINT player_fgs_sane         CHECK (field_goals_made <= field_goals_attempted),
    CONSTRAINT player_xps_sane         CHECK (extra_points_made <= extra_points_attempted)
);

CREATE INDEX player_game_stats_player_idx   ON player_game_stats (player_id);
CREATE INDEX player_game_stats_team_idx     ON player_game_stats (team_id);
CREATE INDEX player_game_stats_opponent_idx ON player_game_stats (opponent_id);

-- The splits index. "Peyton against Jacksonville" without touching games.
CREATE INDEX player_game_stats_matchup_idx
    ON player_game_stats (player_id, opponent_id);

-- ------------------------------------------------------------ integrity

-- opponent_id and is_home are denormalized: the same facts live in games.
-- Postgres cannot express a cross-table CHECK, so this trigger keeps the
-- two in sync. Without it, a typo in an insert silently produces stat
-- lines attributed to a matchup that never happened.
CREATE OR REPLACE FUNCTION assert_stat_matchup() RETURNS trigger AS $$
DECLARE
    home text;
    away text;
BEGIN
    SELECT home_team_id, away_team_id INTO home, away
    FROM games WHERE id = NEW.game_id;

    IF NEW.team_id = home THEN
        IF NEW.opponent_id <> away OR NOT NEW.is_home THEN
            RAISE EXCEPTION
                'game % : team % is home, expected opponent % and is_home true',
                NEW.game_id, NEW.team_id, away;
        END IF;
    ELSIF NEW.team_id = away THEN
        IF NEW.opponent_id <> home OR NEW.is_home THEN
            RAISE EXCEPTION
                'game % : team % is away, expected opponent % and is_home false',
                NEW.game_id, NEW.team_id, home;
        END IF;
    ELSE
        RAISE EXCEPTION 'game % : team % did not play in it', NEW.game_id, NEW.team_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER team_game_stats_matchup_check
    BEFORE INSERT OR UPDATE ON team_game_stats
    FOR EACH ROW EXECUTE FUNCTION assert_stat_matchup();

CREATE TRIGGER player_game_stats_matchup_check
    BEFORE INSERT OR UPDATE ON player_game_stats
    FOR EACH ROW EXECUTE FUNCTION assert_stat_matchup();

-- ---------------------------------------------------------------- views

-- Stat lines with season and week attached, so splits queries do not have
-- to spell out the join every time.
CREATE VIEW player_game_stats_full AS
SELECT
    pgs.*,
    g.season_id,
    g.week,
    g.is_playoff,
    g.played_at
FROM player_game_stats pgs
JOIN games g ON g.id = pgs.game_id;

CREATE VIEW team_game_stats_full AS
SELECT
    tgs.*,
    g.season_id,
    g.week,
    g.is_playoff,
    g.played_at
FROM team_game_stats tgs
JOIN games g ON g.id = tgs.game_id;

COMMIT;
