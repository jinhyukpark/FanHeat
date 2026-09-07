import test from 'node:test'
import assert from 'node:assert/strict'
import { calculateHeatSnapshot, applyHeatActivity, calculateFanLevel, calculateFanRank } from '../src/lib/fan-stats.js'

test('empty and invalid heat has zero TTL', () => {
  for (const value of [{}, { heatRange: 80 }, { heatRange: 80, lastActivityAt: 'invalid' }]) {
    assert.equal(calculateHeatSnapshot(value).daysRemaining, 0)
  }
})
test('heat decay and expiry', () => {
  const state = { heatRange: 80, lastActivityAt: '2026-01-01T00:00:00Z' }
  assert.equal(calculateHeatSnapshot(state, new Date('2026-01-16T00:00:00Z')).heatRange, 40)
  assert.equal(calculateHeatSnapshot(state, new Date('2026-01-31T00:00:00Z')).daysRemaining, 0)
})
test('MAX counts crossings, not activities while full', () => {
  let state = {}
  for (let n = 0; n < 7; n++) state = applyHeatActivity(state, 'post', new Date('2026-01-01'))
  assert.equal(state.heatRange, 100)
  assert.equal(state.heatMaxCount, 1)
})
test('level boundaries and progress do not prematurely reach 100%', () => {
  assert.deepEqual(calculateFanLevel(0), { level: 1, progress: 0, creditToNextLevel: 100 })
  assert.equal(calculateFanLevel(100).level, 2)
  assert.equal(calculateFanLevel(399).progress, 99)
  assert.equal(calculateFanLevel(400).level, 3)
})
test('unranked and ranked totals', () => {
  assert.deepEqual(calculateFanRank(0, 10), { position: 0, total: 10, topPercent: 0 })
  assert.equal(calculateFanRank(2, 10).topPercent, 20)
})
