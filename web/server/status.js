import { createHash, timingSafeEqual } from "node:crypto"

const STATES = new Set(["EMPTY", "OCCUPIED", "AWAY", "ABANDONED"])
const STALE_AFTER_MS = 30_000
const MAX_BODY = 128 * 1024
const ISO_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$/

function shortText(value, length) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= length &&
    !/[\u0000-\u001f\u007f]/u.test(value)
}

// Copy only publishable fields. Camera frames, coordinates and unrecognized metadata
// are never persisted or returned to public visitors.
function normalize(body, now) {
  if (!body || typeof body.observedAt !== "string" || !ISO_TIME.test(body.observedAt)) return null
  const mode = body.mode === undefined ? "live" : body.mode
  if (mode !== "live" && mode !== "demo") return null
  const millis = Date.parse(body.observedAt)
  if (!Number.isFinite(millis) || millis > now + 5000) return null
  if (!Array.isArray(body.seats) || !body.seats.length || body.seats.length > 128) return null
  const seats = []
  const ids = new Set()
  for (const seat of body.seats) {
    if (!seat || !shortText(seat.id, 64) || ids.has(seat.id) ||
        !shortText(seat.label, 80) || !STATES.has(seat.state)) return null
    if (!Number.isSafeInteger(seat.awaySeconds) || seat.awaySeconds < 0) return null
    const items = seat.items === undefined ? [] : seat.items
    if (!Array.isArray(items) || items.length > 64 || !items.every(item => shortText(item, 64))) return null
    ids.add(seat.id)
    seats.push({ id: seat.id, label: seat.label, state: seat.state,
      awaySeconds: seat.awaySeconds, items: [...new Set(items)] })
  }
  return { observedAt: new Date(millis).toISOString(), mode, seats }
}

function authorized(header, token) {
  const digest = value => createHash("sha256").update(value).digest()
  return timingSafeEqual(digest(header || ""), digest(`Bearer ${token}`))
}

function reply(status, data, extraHeaders = {}) {
  return Response.json(data, { status, headers: { "Cache-Control": "no-store", ...extraHeaders } })
}

async function readBody(request) {
  const chunks = []
  let bytes = 0
  for await (const chunk of request.body || []) {
    bytes += chunk.length
    if (bytes > MAX_BODY) return { status: 413 }
    chunks.push(chunk)
  }
  try {
    return { body: JSON.parse(Buffer.concat(chunks).toString("utf8")) }
  } catch {
    return { status: 400 }
  }
}

export function createHandler(store, env, clock = Date.now) {
  return async request => {
    try {
      if (request.method === "GET") {
        const snapshot = await store.read()
        const now = clock()
        const stale = !snapshot || now - Date.parse(snapshot.observedAt) >= STALE_AFTER_MS
        return reply(200, { snapshot, stale, serverTime: new Date(now).toISOString() })
      }
      if (request.method !== "POST") {
        return reply(405, { error: "Method not allowed" }, { Allow: "GET, POST" })
      }
      if (!env.MONITOR_TOKEN) return reply(503, { error: "Writer not configured" })
      if (!authorized(request.headers.get("Authorization"), env.MONITOR_TOKEN)) {
        return reply(401, { error: "Unauthorized" })
      }
      if (request.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "application/json") {
        return reply(415, { error: "Expected application/json" })
      }
      if (Number(request.headers.get("Content-Length")) > MAX_BODY) return reply(413, { error: "Payload too large" })
      const { body, status } = await readBody(request)
      if (status) return reply(status, { error: status === 413 ? "Payload too large" : "Invalid JSON" })
      const snapshot = normalize(body, clock())
      if (!snapshot) return reply(400, { error: "Invalid observation or device clock" })
      await store.write(snapshot)
      return reply(200, { ok: true })
    } catch {
      return reply(503, { error: "Status service unavailable" })
    }
  }
}
