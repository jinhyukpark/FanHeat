const DAY_MS = 24 * 60 * 60 * 1000

export const HEAT_WINDOW_DAYS = 30

export const HEAT_ACTIVITY_WEIGHTS = Object.freeze({
  post: 18,
  friendship: 12,
  comment: 6,
  gallery: 4,
  bookmark: 3,
  vote: 2,
})

const validDate = (value, fallback = new Date()) => {
  const date = new Date(value || fallback)
  return Number.isNaN(date.getTime()) ? fallback : date
}

export function calculateHeatSnapshot({ heatRange = 0, lastActivityAt }, now = new Date()) {
  const currentTime = validDate(now)
  if (!lastActivityAt || Number.isNaN(new Date(lastActivityAt).getTime()) || !(Number(heatRange) > 0)) {
    return { heatRange: 0, daysRemaining: 0, expiresAt: null }
  }
  const activityTime = validDate(lastActivityAt, currentTime)
  const elapsedDays = Math.max(0, (currentTime.getTime() - activityTime.getTime()) / DAY_MS)
  const remainingRatio = Math.max(0, 1 - elapsedDays / HEAT_WINDOW_DAYS)
  const heat = Math.round(Math.max(0, Math.min(100, Number(heatRange) || 0)) * remainingRatio)
  return {
    heatRange: heat,
    daysRemaining: heat > 0 ? Math.max(0, Math.min(HEAT_WINDOW_DAYS, Math.ceil(HEAT_WINDOW_DAYS - elapsedDays))) : 0,
    expiresAt: new Date(activityTime.getTime() + HEAT_WINDOW_DAYS * DAY_MS),
  }
}

export function applyHeatActivity(state, activityType, occurredAt = new Date()) {
  const activityTime = validDate(occurredAt)
  const current = calculateHeatSnapshot({ heatRange: state.heatRange, lastActivityAt: state.lastActivityAt }, activityTime)
  const nextHeat = Math.min(100, current.heatRange + (HEAT_ACTIVITY_WEIGHTS[activityType] || 0))
  const reachedMax = current.heatRange < 100 && nextHeat === 100
  return {
    heatRange: nextHeat,
    heatMaxCount: Math.max(0, Number(state.heatMaxCount) || 0) + (reachedMax ? 1 : 0),
    lastActivityAt: activityTime.toISOString(),
    expiresAt: new Date(activityTime.getTime() + HEAT_WINDOW_DAYS * DAY_MS).toISOString(),
  }
}

export function calculateFanLevel(fanCredit = 0) {
  const credit = Math.max(0, Number(fanCredit) || 0)
  const level = Math.floor(Math.sqrt(credit / 100)) + 1
  const currentMinimum = 100 * (level - 1) ** 2
  const nextMinimum = 100 * level ** 2
  return {
    level,
    progress: Math.min(99, Math.floor((credit - currentMinimum) / Math.max(1, nextMinimum - currentMinimum) * 100)),
    creditToNextLevel: Math.max(0, nextMinimum - credit),
  }
}

export function calculateFanRank(position = 0, total = 0) {
  const safeTotal = Math.max(0, Number(total) || 0)
  const requestedPosition = Math.max(0, Number(position) || 0)
  if (!safeTotal || !requestedPosition) return { position: 0, total: safeTotal, topPercent: 0 }
  const safePosition = Math.min(safeTotal, requestedPosition)
  return { position: safePosition, total: safeTotal, topPercent: Math.max(1, Math.ceil(safePosition / safeTotal * 100)) }
}
