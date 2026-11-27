import assert from "node:assert/strict"
import { execFile } from "node:child_process"
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { promisify } from "node:util"

const exec = promisify(execFile)
const launcher = fileURLToPath(new URL("../dev.mjs", import.meta.url))

test("camera uses the active Python environment and preserves capture arguments", {
  skip: process.platform === "win32",
}, async t => {
  const venv = await mkdtemp(join(tmpdir(), "cafe-camera-venv-"))
  t.after(() => rm(venv, { recursive: true, force: true }))
  await mkdir(join(venv, "bin"))
  await writeFile(join(venv, "bin/python"), '#!/bin/sh\nprintf "%s\\n" "$@"\n', { mode: 0o755 })
  const { stdout } = await exec(process.execPath, [launcher, "--camera", "--source", "test clip.mp4"], {
    env: { ...process.env, VIRTUAL_ENV: venv, PORT: "3087" },
  })
  assert.deepEqual(stdout.trim().split("\n"), [
    "-u", "-m", "cafe_monitor", "--viewer", "--viewer-port", "3087", "--source", "test clip.mp4",
  ])
})
