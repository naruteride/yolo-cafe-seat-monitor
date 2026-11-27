const get = id => document.getElementById(id)
const states = { EMPTY: "이용 가능", OCCUPIED: "이용 중", AWAY: "일시 비움", ABANDONED: "장기 방치" }
const itemNames = new Map(Object.entries({
  backpack: "백팩", handbag: "핸드백", cup: "컵", laptop: "노트북", pencil: "연필",
  pen: "펜", book: "책", bottle: "병", "cell phone": "휴대전화",
}))
const dateFormat = new Intl.DateTimeFormat("ko-KR", {
  timeZone: "Asia/Seoul", year: "numeric", month: "short", day: "numeric",
  hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
})
const connection = get("connection")
const notice = get("notice")
const list = get("seat-list")
const filter = get("filter")
const refreshButton = get("refresh")
let snapshot = null
let stale = true
let failed = false
let fetching = false

function duration(seconds) {
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor(seconds / 60) % 60
  if (hours) return `${hours}시간 ${mins}분`
  if (mins) return `${mins}분 ${seconds % 60}초`
  return `${seconds}초`
}

function cell(tag, className, value) {
  const node = document.createElement(tag)
  node.className = className
  node.textContent = value
  return node
}

function seatRow(seat) {
  const row = document.createElement("li")
  row.className = "seat-row"
  const items = seat.items.map(item => itemNames.get(item) || item).join(", ") || "없음"
  const away = seat.state === "AWAY" || seat.state === "ABANDONED"
  const elapsed = cell("span", "elapsed", away ? duration(seat.awaySeconds) : "—")
  elapsed.dataset.away = String(away)
  row.append(cell("strong", "seat-title", seat.label),
    cell("span", "badge " + seat.state.toLowerCase(), states[seat.state]),
    cell("span", "items", items), elapsed)
  return row
}

function render() {
  const seats = snapshot?.seats || []
  const current = snapshot && !stale && !failed
  const demo = snapshot?.mode === "demo"
  let status = "센서 연결 대기"
  if (failed) status = "서비스 연결 지연"
  else if (current) status = demo ? "시연 데이터" : "센서 연결됨"
  else if (snapshot) status = demo ? "시연 신호 지연" : "센서 신호 지연"
  connection.textContent = status
  connection.className = "connection" + (current ? " live" : failed || snapshot ? " warn" : "")
  if (snapshot) {
    const note = current ? "최근 관측" : "마지막 관측"
    get("observed").textContent = (demo ? "시연 데이터 · " : "") + note + "  " +
      dateFormat.format(new Date(snapshot.observedAt)) + " (한국시간)"
  } else {
    get("observed").textContent = failed ? "현황 서버에 연결할 수 없습니다." : "첫 번째 센서 관측을 기다리고 있습니다."
  }
  for (const state of Object.keys(states)) {
    get("count-" + state.toLowerCase()).textContent = current ? seats.filter(s => s.state === state).length : "—"
  }
  get("capacity").textContent = snapshot ? `전체 ${seats.length}석` : "전체 좌석 미확인"
  get("details-title").textContent = snapshot && !current ? "마지막으로 관측한 좌석" : "좌석별 현황"
  const filtered = seats.filter(seat => !filter.value || seat.state === filter.value)
  filter.disabled = !snapshot
  list.replaceChildren(...filtered.map(seatRow))
  notice.hidden = filtered.length > 0
  if (!notice.hidden) {
    if (snapshot) {
      get("notice-title").textContent = "선택한 상태의 좌석이 없습니다"
      get("notice-text").textContent = "다른 상태를 선택해 주세요."
    } else if (failed) {
      get("notice-title").textContent = "좌석 현황을 불러올 수 없습니다"
      get("notice-text").textContent = "잠시 후 자동으로 다시 연결합니다."
    } else {
      get("notice-title").textContent = "아직 관측된 좌석이 없습니다"
      get("notice-text").textContent = "카페 센서가 첫 관측을 보내면 좌석이 표시됩니다."
    }
  }
}

async function refresh() {
  if (fetching) return
  fetching = true
  refreshButton.disabled = true
  try {
    const response = await fetch("/api/status", { cache: "no-store", signal: AbortSignal.timeout(6000) })
    if (!response.ok) throw new Error("status unavailable")
    const data = await response.json()
    snapshot = data.snapshot
    stale = data.stale
    failed = false
  } catch {
    failed = true
  } finally {
    fetching = false
    refreshButton.disabled = false
    render()
  }
}

filter.addEventListener("change", render)
refreshButton.addEventListener("click", refresh)
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh() })
setInterval(() => { if (!document.hidden) refresh() }, 5000)
refresh()
