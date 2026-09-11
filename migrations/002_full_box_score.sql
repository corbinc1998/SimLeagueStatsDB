BEGIN;
DROP VIEW player_game_stats_full;
DROP VIEW team_game_stats_full;
-- ---------------------------------------------------------------- core

ALTER TABLE player_game_stats
RENAME COLUMN tackles TO solo_tackles;

ALTER TABLE player_game_stats
DROP COLUMN return_touchdowns;

ALTER TABLE player_game_stats
    ADD COLUMN pass_long smallint Not NUll DEFAULT 0,
    ADD COLUMN broken_tackles smallint Not NUll DEFAULT 0,
    ADD COLUMN yards_after_first_hit smallint Not NUll DEFAULT 0,
    ADD COLUMN rushes_20_plus smallint Not NUll DEFAULT 0,
    ADD COLUMN rush_long smallint Not NUll DEFAULT 0,
    ADD COLUMN yards_after_catch smallint Not NUll DEFAULT 0,
    ADD COLUMN drops smallint Not NUll DEFAULT 0,
    ADD COLUMN reception_long smallint Not NUll DEFAULT 0,
    ADD COLUMN pancakes smallint Not NUll DEFAULT 0,
    ADD COLUMN sacks_allowed smallint Not NUll DEFAULT 0,
    ADD COLUMN assisted_tackles smallint Not NUll DEFAULT 0,
    ADD COLUMN interception_yards smallint Not NUll DEFAULT 0,
    ADD COLUMN interception_long smallint Not NUll DEFAULT 0,
    ADD COLUMN fumble_return_yards smallint Not NUll DEFAULT 0,
    ADD COLUMN blocked_kicks smallint Not NUll DEFAULT 0,
    ADD COLUMN safeties smallint Not NUll DEFAULT 0,
    ADD COLUMN field_goal_long smallint Not NUll DEFAULT 0,
    ADD COLUMN field_goals_blocked smallint Not NUll DEFAULT 0,
    ADD COLUMN extra_points_blocked smallint Not NUll DEFAULT 0,
    ADD COLUMN fga_29 smallint Not NUll DEFAULT 0,
    ADD COLUMN fgm_29 smallint Not NUll DEFAULT 0,
    ADD COLUMN fga_39 smallint Not NUll DEFAULT 0,
    ADD COLUMN fgm_39 smallint Not NUll DEFAULT 0,
    ADD COLUMN fga_49 smallint Not NUll DEFAULT 0,
    ADD COLUMN fgm_49 smallint Not NUll DEFAULT 0,
    ADD COLUMN fga_50_plus smallint Not NUll DEFAULT 0,
    ADD COLUMN fgm_50_plus smallint Not NUll DEFAULT 0,
    ADD COLUMN kickoffs smallint Not NUll DEFAULT 0,
    ADD COLUMN touchbacks smallint Not NUll DEFAULT 0,
    ADD COLUMN punt_net_yards smallint Not NUll DEFAULT 0,
    ADD COLUMN punts_blocked smallint Not NUll DEFAULT 0,
    ADD COLUMN punts_inside_20 smallint Not NUll DEFAULT 0,
    ADD COLUMN punt_touchbacks smallint Not NUll DEFAULT 0,
    ADD COLUMN punt_long smallint Not NUll DEFAULT 0,
    ADD COLUMN kick_return_long smallint Not NUll DEFAULT 0,
    ADD COLUMN punt_return_long smallint Not NUll DEFAULT 0,
    ADD COLUMN kick_return_touchdowns smallint Not NUll DEFAULT 0,
    ADD COLUMN punt_return_touchdowns smallint Not NUll DEFAULT 0;

ALTER table team_game_stats
    ADD COLUMN total_offense smallint Not NUll DEFAULT 0,
    ADD COLUMN kick_return_yards smallint Not NUll DEFAULT 0,
    ADD COLUMN punt_return_yards smallint Not NUll DEFAULT 0,
    ADD COLUMN two_point_conversions_made smallint Not NUll DEFAULT 0,
    ADD COLUMN two_point_conversions_attempted smallint Not NUll DEFAULT 0,
    ADD COLUMN redzone_trips smallint Not NUll DEFAULT 0,
    ADD COLUMN redzone_touchdowns smallint Not NUll DEFAULT 0,
    ADD COLUMN redzone_field_goals smallint Not NUll DEFAULT 0;


ALTER TABLE player_game_stats
    ADD CONSTRAINT fg_29_sane CHECK (fgm_29 <= fga_29),
    ADD CONSTRAINT fg_39_sane CHECK (fgm_39 <= fga_39),
    ADD CONSTRAINT fg_49_sane CHECK (fgm_49 <= fga_49),
    ADD CONSTRAINT fg_50_plus_sane CHECK (fgm_50_plus <= fga_50_plus),
    ADD CONSTRAINT punts_inside_20_sane CHECK (punts_inside_20 <= punts),
    ADD CONSTRAINT punt_touchbacks_sane CHECK (punt_touchbacks <= punts),
    ADD CONSTRAINT touchbacks_sane CHECK (touchbacks <= kickoffs);

ALTER TABLE team_game_stats
    ADD CONSTRAINT two_point_sane CHECK (two_point_conversions_made <= two_point_conversions_attempted),
    ADD CONSTRAINT redzone_sane CHECK (redzone_touchdowns + redzone_field_goals <= redzone_trips);



CREATE VIEW player_game_stats_full AS
SELECT pgs.*, g.season_id, g.week, g.is_playoff, g.played_at
FROM player_game_stats pgs JOIN games g ON g.id = pgs.game_id;

CREATE VIEW team_game_stats_full AS
SELECT tgs.*, g.season_id, g.week, g.is_playoff, g.played_at
FROM team_game_stats tgs JOIN games g ON g.id = tgs.game_id;
COMMIT;

    