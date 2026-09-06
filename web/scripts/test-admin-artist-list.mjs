import assert from 'node:assert/strict'
import { artistStatus, filterAdminArtists } from '../src/lib/admin-artist-list.js'

const rows = [
  { id: 1, name: 'Old public', active: true, created_at: '2025-01-01' },
  { id: 2, name: 'Private', active: false, review_pending: false, created_at: '2026-01-01' },
  { id: 3, name: 'New pending', agency: 'Agency', active: false, review_pending: true, created_at: '2026-02-01', artist_correction_requests: [{ status: 'pending' }] },
  { id: 4, name: 'Newest public', active: true, created_at: '2026-02-01' },
]
assert.deepEqual(filterAdminArtists(rows).map(r => r.id), [4, 3, 2, 1])
assert.deepEqual(rows.map(r => r.id), [1, 2, 3, 4])
assert.equal(artistStatus(rows[0]), 'published')
assert.equal(artistStatus(rows[1]), 'private')
assert.equal(artistStatus(rows[2]), 'pending')
assert.deepEqual(filterAdminArtists(rows, { status: 'published' }).map(r => r.id), [4, 1])
assert.deepEqual(filterAdminArtists(rows, { status: 'private' }).map(r => r.id), [2])
assert.deepEqual(filterAdminArtists(rows, { status: 'pending', query: 'AGENCY', requestsOnly: true }).map(r => r.id), [3])
assert.equal(filterAdminArtists(rows, { status: 'private', requestsOnly: true }).length, 0)
console.log('Artist latest-first ordering, status filters, search and request-filter combinations passed.')
