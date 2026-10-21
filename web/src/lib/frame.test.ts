import { describe, it, expect } from 'vitest'
import { toDisplay, PITCH_L, PITCH_W } from './frame.ts'

describe('toDisplay', () => {
  it('returns coordinates unchanged when possessing team is home', () => {
    expect(toDisplay(80, 40, 'T01', 'T01')).toEqual([80, 40])
    expect(toDisplay(0, 0, 'T01', 'T01')).toEqual([0, 0])
    expect(toDisplay(105, 68, 'T01', 'T01')).toEqual([105, 68])
  })

  it('mirrors coordinates when possessing team is away', () => {
    expect(toDisplay(80, 40, 'T02', 'T01')).toEqual([PITCH_L - 80, PITCH_W - 40])
    expect(toDisplay(0, 0, 'T02', 'T01')).toEqual([PITCH_L, PITCH_W])
    expect(toDisplay(105, 68, 'T02', 'T01')).toEqual([0, 0])
  })

  it('double-flip returns original', () => {
    const [x1, y1] = toDisplay(60, 30, 'T02', 'T01')
    const [x2, y2] = toDisplay(x1, y1, 'T02', 'T01')
    expect(x2).toBeCloseTo(60)
    expect(y2).toBeCloseTo(30)
  })

  it('center of pitch is invariant', () => {
    const cx = PITCH_L / 2, cy = PITCH_W / 2
    expect(toDisplay(cx, cy, 'T01', 'T01')).toEqual([cx, cy])
    const [mx, my] = toDisplay(cx, cy, 'T02', 'T01')
    expect(mx).toBeCloseTo(cx)
    expect(my).toBeCloseTo(cy)
  })
})
