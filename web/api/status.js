import { createHandler } from "../server/status.js"
import { redisStore } from "../server/store.js"

export default { fetch: createHandler(redisStore(process.env), process.env) }
