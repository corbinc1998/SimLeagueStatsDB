// Each franchise's primary and secondary colors.
//
// These are the only saturated colors in the interface — everything else
// is graphite. Colour carries information here rather than decorating:
// the side of the form you are looking at is identified by the team's own
// colours, so you never have to read a label to know whether you are
// entering the home or away line.
//
// 2007 alignment, matching the team ids in the data (oak, sd, stl).

export interface TeamColors {
    primary: string;
    secondary: string;
  }
  
  export const TEAM_COLORS: Record<string, TeamColors> = {
    ari: { primary: "#97233F", secondary: "#000000" },
    atl: { primary: "#A71930", secondary: "#000000" },
    bal: { primary: "#241773", secondary: "#9E7C0C" },
    buf: { primary: "#00338D", secondary: "#C60C30" },
    car: { primary: "#0085CA", secondary: "#101820" },
    chi: { primary: "#0B162A", secondary: "#C83803" },
    cin: { primary: "#FB4F14", secondary: "#000000" },
    cle: { primary: "#311D00", secondary: "#FF3C00" },
    dal: { primary: "#003594", secondary: "#869397" },
    den: { primary: "#FB4F14", secondary: "#002244" },
    det: { primary: "#0076B6", secondary: "#B0B7BC" },
    gb: { primary: "#203731", secondary: "#FFB612" },
    hou: { primary: "#03202F", secondary: "#A71930" },
    ind: { primary: "#002C5F", secondary: "#A2AAAD" },
    jax: { primary: "#006778", secondary: "#D7A22A" },
    kc: { primary: "#E31837", secondary: "#FFB81C" },
    mia: { primary: "#008E97", secondary: "#FC4C02" },
    min: { primary: "#4F2683", secondary: "#FFC62F" },
    ne: { primary: "#002244", secondary: "#C60C30" },
    no: { primary: "#101820", secondary: "#D3BC8D" },
    nyg: { primary: "#0B2265", secondary: "#A71930" },
    nyj: { primary: "#125740", secondary: "#FFFFFF" },
    oak: { primary: "#000000", secondary: "#A5ACAF" },
    phi: { primary: "#004C54", secondary: "#A5ACAF" },
    pit: { primary: "#FFB612", secondary: "#101820" },
    sd: { primary: "#0080C6", secondary: "#FFC20E" },
    sea: { primary: "#002244", secondary: "#69BE28" },
    sf: { primary: "#AA0000", secondary: "#B3995D" },
    stl: { primary: "#002244", secondary: "#B3995D" },
    tb: { primary: "#D50A0A", secondary: "#34302B" },
    ten: { primary: "#0C2340", secondary: "#4B92DB" },
    was: { primary: "#5A1414", secondary: "#FFB612" },
  };
  
  const FALLBACK: TeamColors = { primary: "#6B7280", secondary: "#9CA3AF" };
  
  export function teamColors(teamId: string): TeamColors {
    return TEAM_COLORS[teamId] ?? FALLBACK;
  }
  
  // A few primaries are near-black (Oakland is literally black, Chicago and
  // New Orleans nearly so). Against a graphite panel those read as absence
  // rather than as a team, so the secondary carries the identity instead.
  //
  // The threshold is deliberately low. Navy and purple are dark but plainly
  // visible here, and they are what those teams look like — swapping them
  // out would be the design overriding the data, which is the opposite of
  // the rule this interface follows.
  const TOO_DARK = 0.015;
  
  export function accentFor(teamId: string): string {
    const { primary, secondary } = teamColors(teamId);
    return relativeLuminance(primary) < TOO_DARK ? secondary : primary;
  }
  
  function relativeLuminance(hex: string): number {
    const value = hex.replace("#", "");
    const channels = [0, 2, 4].map((i) => {
      const c = parseInt(value.slice(i, i + 2), 16) / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    return (
      0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
    );
  }