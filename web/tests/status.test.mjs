import assert from "node:assert/strict"
import test from "node:test"
import { createHandler } from "../server/status.js"
import { memoryStore, redisStore } from "../server/store.js"

const url = "http://localhost/api/status"
const token = "local-test"
const observedAt = "2026-11-27T01:00:00.000Z"
const start = Date.parse(observedAt)
const seat = { id: "A", label: "창가 1", state: "AWAY", awaySeconds: 10, items: ["cup"] }
const sample = { observedAt, seats: [seat] }
function post(body, key = token) {
  return new Request(url, { method: "POST", headers: {
    Authorization: `Bearer ${key}`, "Content-Type": "application/json",
  }, body: JSON.stringify(body) })
}
const get = () => new Request(url)

test("authenticated writes expose only the allowed fields and retain the demo marker", async () => {
  const handler = createHandler(memoryStore(), { MONITOR_TOKEN: token }, () => start)
  assert.equal((await handler(post(sample, "incorrect"))).status, 401)
  assert.equal((await (await handler(get())).json()).snapshot, null)
  const submission = { ...sample, mode: "demo", image: "private", seats: [{ ...seat, box: [1, 2, 3, 4] }] }
  assert.equal((await handler(post(submission))).status, 200)
  const response = await handler(get())
  assert.equal(response.headers.get("Cache-Control"), "no-store")
  assert.deepEqual(await response.json(), {
    snapshot: { ...sample, mode: "demo" }, serverTime: observedAt, stale: false,
  })
})

test("duplicate and delayed observations cannot replace later data or extend freshness", async () => {
  let now = start
  const handler = createHandler(memoryStore(), { MONITOR_TOKEN: token }, () => now)
  await handler(post(sample))
  now += 30_000
  for (const timestamp of [observedAt, new Date(start - 1000).toISOString()]) {
    const res = await handler(post({ observedAt: timestamp, seats: [{ ...seat, state: "EMPTY" }] }))
    assert.equal(res.status, 200)
  }
  const { snapshot, stale } = await (await handler(get())).json()
  assert.equal(snapshot.seats[0].state, "AWAY")
  assert.equal(snapshot.mode, "live")
  assert.equal(stale, true)
})

test("invalid readings are rejected and leave the last observation intact", async () => {
  const handler = createHandler(memoryStore(), { MONITOR_TOKEN: token }, () => start)
  for (const fields of [
    { mode: "test" }, { seats: [seat, seat] }, { observedAt: "bad" },
    { observedAt: new Date(start + 60_000).toISOString() },
    { seats: [{ ...seat, state: "NEW" }] }, { seats: [{ ...seat, items: "backpack" }] },
  ]) {
    assert.equal((await handler(post({ ...sample, ...fields }))).status, 400)
  }
  assert.equal((await handler(post({ ...sample, image: "x".repeat(140_000) }))).status, 413)
  assert.equal((await (await handler(get())).json()).snapshot, null)
})

test("deployment requires configured storage and writer credentials", async () => {
  const handler = createHandler(redisStore({}), {}, () => start)
  assert.equal((await handler(get())).status, 503)
  assert.equal((await handler(post(sample))).status, 503)
  assert.equal((await handler(new Request(url, { method: "DELETE" }))).status, 405)
})
