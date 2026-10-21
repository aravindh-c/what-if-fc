export const PITCH_L = 105
export const PITCH_W = 68

/**
 * Convert (x, y) from a possession frame to the display frame.
 *
 * Home team always attacks toward display x = 105.
 * When the possessing team is the away team their frame is
 * mirrored: x' = 105 − x, y' = 68 − y.
 */
export function toDisplay(
  x: number,
  y: number,
  possessingTeam: string,
  homeTeam: string,
): [number, number] {
  if (possessingTeam === homeTeam) return [x, y]
  return [PITCH_L - x, PITCH_W - y]
}

/** Format match_clock_s as mm:ss */
export function fmtClock(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}
