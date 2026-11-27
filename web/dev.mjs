import { createServer } from "node:http"
import { readFile } from "node:fs/promises"
import { Readable } from "node:stream"
import { randomBytes } from "node:crypto"
import { spawn } from "node:child_process"
import { createHandler } from "./server/status.js"
import { memoryStore } from "./server/store.js"

const demo = process.argv.includes("--demo")
const token = demo ? randomBytes(32).toString("hex") : process.env.MONITOR_TOKEN
const status = createHandler(memoryStore(), { MONITOR_TOKEN: token })
const assets = new Map([
  ["/", ["index.html", "text/html"]],
  ["/board.css", ["board.css", "text/css"]],
  ["/board.js", ["board.js", "text/javascript"]],
])
const port = Number(process.env.PORT || 3000)
const server = createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://127.0.0.1")
    if (url.pathname === "/api/status") {
      const options = { method: req.method, headers: req.headers }
      if (req.method !== "GET" && req.method !== "HEAD") {
        options.body = Readable.toWeb(req)
        options.duplex = "half"
      }
      const response = await status(new Request(url, options))
      res.writeHead(response.status, Object.fromEntries(response.headers))
      res.end(await response.text())
      return
    }
    const asset = assets.get(url.pathname)
    if (!asset || !["GET", "HEAD"].includes(req.method)) {
      res.writeHead(404).end()
      return
    }
    const content = await readFile(new URL("./public/" + asset[0], import.meta.url))
    res.writeHead(200, { "Content-Type": asset[1] + "; charset=utf-8", "Cache-Control": "no-store" })
    res.end(req.method === "HEAD" ? undefined : content)
  } catch {
    res.writeHead(500).end()
  }
})

let writer
let stopping = false
function closeServer() {
  server.close()
  server.closeAllConnections()
}

function stop() {
  if (stopping) return
  stopping = true
  if (writer?.pid && writer.exitCode === null && writer.signalCode === null) {
    // Leave the local HTTP server up while Python flushes its last observation.
    writer.kill("SIGTERM")
    setTimeout(() => {
      if (writer.exitCode === null && writer.signalCode === null) writer.kill("SIGKILL")
    }, 5000).unref()
  } else {
    closeServer()
  }
}

process.on("SIGINT", stop)
process.on("SIGTERM", stop)
server.on("error", error => {
  console.error("로컬 서버를 시작할 수 없습니다.", error.message)
  process.exitCode = 1
  stop()
})
server.listen(port, "127.0.0.1", () => {
  if (stopping) return closeServer()
  const url = `http://127.0.0.1:${server.address().port}`
  console.log(`카페 좌석 현황  ${url}  (로컬 메모리 저장소)`)
  if (!demo) {
    if (!token) console.log("기기 전송을 시험하려면 MONITOR_TOKEN을 설정하고 다시 시작하세요.")
    return
  }
  // Only the local writer's settings are passed to Python. This also prevents
  // inherited deployment credentials or HTTP proxies from redirecting demo data.
  writer = spawn("python3", ["-E", "-s", "-m", "cafe_monitor", "--demo"], {
    cwd: new URL("../", import.meta.url),
    env: { PATH: process.env.PATH, LANG: process.env.LANG || "en_US.UTF-8",
      MONITOR_ENDPOINT: url + "/api/status", MONITOR_TOKEN: token, no_proxy: "*" },
    stdio: ["ignore", "inherit", "inherit"],
  })
  writer.once("error", error => {
    console.error("Python 시연 프로그램을 시작할 수 없습니다.", error.message)
    process.exitCode = 1
    closeServer()
  })
  writer.once("exit", (code, signal) => {
    if (!stopping && (code !== 0 || signal)) {
      console.error("Python 시연 프로그램이 종료되었습니다.", signal || code)
      process.exitCode = code || 1
    }
    closeServer()
  })
})
