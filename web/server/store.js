const KEY = "cafe-monitor:status:v1"

// Compare and replace together so a delayed Pi retry cannot roll the board back.
const REPLACE_IF_NEWER = `
  local previous = redis.call("HGET", KEYS[1], "observedAt")
  if previous and previous >= ARGV[1] then return 0 end
  redis.call("HSET", KEYS[1], "observedAt", ARGV[1], "snapshot", ARGV[2])
  return 1
`

export function redisStore(env) {
  async function command(args) {
    const url = env.UPSTASH_REDIS_REST_URL || env.KV_REST_API_URL
    const token = env.UPSTASH_REDIS_REST_TOKEN || env.KV_REST_API_TOKEN
    if (!url || !token) throw new Error("Redis credentials missing")
    const res = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(args),
      signal: AbortSignal.timeout(4500),
      redirect: "error",
    })
    if (!res.ok) throw new Error("Redis unavailable")
    const reply = await res.json()
    if (reply.error || !Object.hasOwn(reply, "result")) throw new Error("Redis command failed")
    return reply.result
  }
  return {
    async read() {
      const snapshot = await command(["HGET", KEY, "snapshot"])
      return snapshot === null ? null : JSON.parse(snapshot)
    },
    async write(snapshot) {
      await command(["EVAL", REPLACE_IF_NEWER, "1", KEY, snapshot.observedAt, JSON.stringify(snapshot)])
    },
  }
}

export function memoryStore() {
  let current = null
  return {
    read: () => current,
    write(snapshot) {
      if (!current || current.observedAt < snapshot.observedAt) current = snapshot
    },
  }
}
