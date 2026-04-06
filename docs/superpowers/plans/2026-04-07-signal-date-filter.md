# Signal Date Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 시그널 목록을 날짜별로 조회할 수 있도록 캘린더 팝업과 날짜 네비게이션을 추가한다.

**Architecture:** 기존 `/api/<market>/signals` 엔드포인트에 `?date=` 쿼리 파라미터를 추가하고, 캘린더 표시용 `/api/<market>/signals/dates` 엔드포인트를 신규 추가한다. 프론트엔드에서는 시그널 목록 헤더에 날짜 네비게이션(◀ 날짜 ▶)과 캘린더 팝업을 추가하고, localStorage로 마켓별 선택 날짜를 기억한다.

**Tech Stack:** Python/Flask (backend), Vanilla JS/HTML/Tailwind CSS (frontend), SQLAlchemy (ORM)

**Spec:** `docs/superpowers/specs/2026-04-07-signal-date-filter-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `web/app.py` | Modify (lines 121-178) | `api_signals`에 date 파라미터 추가, `api_signals_summary`에 date 파라미터 추가, `api_signals_dates` 신규 |
| `web/templates/index.html` | Modify | 시그널 목록 헤더 날짜 네비게이션, 캘린더 팝업 HTML/CSS/JS, loadSignals/loadSummary date 연동 |
| `tests/test_web_api.py` | Create | API 엔드포인트 테스트 |

---

### Task 1: API — signals/dates 엔드포인트 추가

**Files:**

- Create: `tests/test_web_api.py`
- Modify: `web/app.py:150` (signals/summary 앞에 추가)

- [ ] **Step 1: Write the failing test for signals/dates endpoint**

Create `tests/test_web_api.py`:

```python
"""Tests for web API endpoints — signal date filter feature."""

import json
from datetime import date, timedelta

import pytest
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from db.models import Base, Signal
from web.app import app


@pytest.fixture
def client(tmp_path):
    """Create a test client with in-memory DB."""
    from db import database
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session = Session(engine)

    # Insert test signals across 3 dates
    dates = [date(2026, 4, 6), date(2026, 4, 3), date(2026, 4, 1)]
    for d in dates:
        for sym, sig_type, conf in [("AAPL", "buy", 85), ("MSFT", "watch", 40)]:
            session.add(Signal(
                symbol=sym, market="us", date=d,
                signal_type=sig_type, price=100.0,
                reason="test", confidence=conf, notified=False,
            ))
    session.commit()

    # Monkey-patch get_session to return our test session
    original_get_session = database.get_session
    database.get_session = lambda: session

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c

    database.get_session = original_get_session
    session.close()
    engine.dispose()


class TestSignalDates:
    def test_returns_dates_descending(self, client):
        resp = client.get("/api/us/signals/dates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "dates" in data
        assert data["dates"] == ["2026-04-06", "2026-04-03", "2026-04-01"]

    def test_returns_empty_for_unknown_market(self, client):
        resp = client.get("/api/xx/signals/dates")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dates"] == []

    def test_limited_to_90_days(self, client):
        """Dates older than 90 days should not appear."""
        resp = client.get("/api/us/signals/dates")
        data = resp.get_json()
        # All test dates are within 90 days, so all 3 should appear
        assert len(data["dates"]) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. python3 -m pytest tests/test_web_api.py::TestSignalDates -v`

Expected: FAIL — endpoint `/api/us/signals/dates` returns 404.

- [ ] **Step 3: Implement signals/dates endpoint**

In `web/app.py`, add the following endpoint **before** the `api_signals_summary` function (around line 150):

```python
@app.route("/api/<market>/signals/dates")
def api_signals_dates(market: str):
    """Return list of dates that have signals, descending, limited to 90 days."""
    session = get_session()
    try:
        cutoff = date.today() - timedelta(days=90)
        stmt = (
            select(Signal.date)
            .where(Signal.market == market, Signal.date >= cutoff)
            .distinct()
            .order_by(Signal.date.desc())
        )
        rows = session.execute(stmt).scalars().all()
        return jsonify({"dates": [d.isoformat() for d in rows]})
    finally:
        session.close()
```

**Important:** This route must be registered before `/api/<market>/signals/summary` because Flask matches routes in registration order and `signals/dates` must not be caught by a different pattern.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. python3 -m pytest tests/test_web_api.py::TestSignalDates -v`

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_web_api.py web/app.py
git commit -m "feat(api): add /api/<market>/signals/dates endpoint"
```

---

### Task 2: API — signals 엔드포인트에 date 파라미터 추가

**Files:**

- Modify: `web/app.py:121-149` (api_signals 함수)
- Modify: `tests/test_web_api.py` (테스트 추가)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_api.py`:

```python
class TestSignalsWithDate:
    def test_filter_by_date(self, client):
        resp = client.get("/api/us/signals?date=2026-04-03")
        data = resp.get_json()
        assert len(data) == 2  # AAPL + MSFT on that date
        assert all(s["date"] == "2026-04-03" for s in data)

    def test_without_date_returns_latest(self, client):
        """No date param → returns signals from most recent date only."""
        resp = client.get("/api/us/signals")
        data = resp.get_json()
        # Most recent date is 2026-04-06, has 2 signals
        assert len(data) == 2
        assert all(s["date"] == "2026-04-06" for s in data)

    def test_invalid_date_returns_empty(self, client):
        resp = client.get("/api/us/signals?date=2026-12-31")
        data = resp.get_json()
        assert data == []

    def test_sorted_by_confidence_desc(self, client):
        resp = client.get("/api/us/signals?date=2026-04-06")
        data = resp.get_json()
        confs = [s["confidence"] for s in data]
        assert confs == sorted(confs, reverse=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python3 -m pytest tests/test_web_api.py::TestSignalsWithDate -v`

Expected: `test_without_date_returns_latest` FAILS (currently returns 7-day range, not latest-only).

- [ ] **Step 3: Modify api_signals to accept date parameter**

Replace the `api_signals` function in `web/app.py` (lines 121-149):

```python
@app.route("/api/<market>/signals")
def api_signals(market: str):
    """Return signals for a specific date, sorted by confidence descending.

    Query params:
        date: ISO date string (e.g. 2026-04-06). If omitted, uses most recent signal date.
    """
    session = get_session()
    try:
        date_str = request.args.get("date")
        if date_str:
            from datetime import datetime as dt
            target_date = dt.strptime(date_str, "%Y-%m-%d").date()
        else:
            # Find most recent signal date
            latest = session.execute(
                select(Signal.date)
                .where(Signal.market == market)
                .order_by(Signal.date.desc())
                .limit(1)
            ).scalar_one_or_none()
            if not latest:
                return jsonify([])
            target_date = latest

        stmt = (
            select(Signal)
            .where(Signal.market == market, Signal.date == target_date)
            .order_by(Signal.confidence.desc())
        )
        rows = session.execute(stmt).scalars().all()

        return jsonify([
            {
                "id": r.id,
                "symbol": r.symbol,
                "date": r.date.isoformat(),
                "signal_type": r.signal_type,
                "price": r.price,
                "target_price": r.target_price,
                "stop_price": r.stop_price,
                "reason": r.reason,
                "confidence": r.confidence,
            }
            for r in rows
        ])
    finally:
        session.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=. python3 -m pytest tests/test_web_api.py::TestSignalsWithDate -v`

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app.py tests/test_web_api.py
git commit -m "feat(api): add date filter to /api/<market>/signals"
```

---

### Task 3: API — signals/summary 엔드포인트에 date 파라미터 추가

**Files:**

- Modify: `web/app.py:152-178` (api_signals_summary 함수)
- Modify: `tests/test_web_api.py` (테스트 추가)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_api.py`:

```python
class TestSignalsSummaryWithDate:
    def test_summary_for_specific_date(self, client):
        resp = client.get("/api/us/signals/summary?date=2026-04-03")
        data = resp.get_json()
        assert data["buy"] == 1
        assert data["watch"] == 1
        assert data["sell"] == 0

    def test_summary_without_date_uses_latest(self, client):
        resp = client.get("/api/us/signals/summary")
        data = resp.get_json()
        # Latest date is 2026-04-06
        assert data["buy"] == 1
        assert data["watch"] == 1

    def test_summary_for_empty_date(self, client):
        resp = client.get("/api/us/signals/summary?date=2099-01-01")
        data = resp.get_json()
        assert data == {"buy": 0, "sell": 0, "watch": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=. python3 -m pytest tests/test_web_api.py::TestSignalsSummaryWithDate -v`

Expected: `test_summary_for_specific_date` FAILS (date param not supported yet).

- [ ] **Step 3: Modify api_signals_summary to accept date parameter**

Replace the `api_signals_summary` function in `web/app.py`:

```python
@app.route("/api/<market>/signals/summary")
def api_signals_summary(market: str):
    """Return buy/sell/watch counts for a specific date.

    Query params:
        date: ISO date string. If omitted, uses most recent signal date.
    """
    session = get_session()
    try:
        date_str = request.args.get("date")
        if date_str:
            from datetime import datetime as dt
            target_date = dt.strptime(date_str, "%Y-%m-%d").date()
        else:
            latest_row = session.execute(
                select(Signal.date)
                .where(Signal.market == market)
                .order_by(Signal.date.desc())
                .limit(1)
            ).scalar_one_or_none()

            if not latest_row:
                return jsonify({"buy": 0, "sell": 0, "watch": 0})
            target_date = latest_row

        stmt = select(Signal).where(Signal.market == market, Signal.date == target_date)
        rows = session.execute(stmt).scalars().all()

        counts = {"buy": 0, "sell": 0, "watch": 0}
        for r in rows:
            if r.signal_type in counts:
                counts[r.signal_type] += 1

        return jsonify(counts)
    finally:
        session.close()
```

- [ ] **Step 4: Run all API tests to verify they pass**

Run: `PYTHONPATH=. python3 -m pytest tests/test_web_api.py -v`

Expected: All tests PASS (TestSignalDates: 3, TestSignalsWithDate: 4, TestSignalsSummaryWithDate: 3 = 10 total).

- [ ] **Step 5: Commit**

```bash
git add web/app.py tests/test_web_api.py
git commit -m "feat(api): add date filter to /api/<market>/signals/summary"
```

---

### Task 4: Frontend — 시그널 목록 헤더에 날짜 네비게이션 HTML/CSS 추가

**Files:**

- Modify: `web/templates/index.html` (HTML lines 84-91, CSS in `<style>`)

- [ ] **Step 1: Add calendar CSS to the style block**

In `web/templates/index.html`, add the following CSS inside the existing `<style>` tag (after the scrollbar styles, before `</style>`):

```css
    /* Calendar popup */
    .cal-overlay { position: fixed; inset: 0; z-index: 40; }
    .cal-popup {
      position: absolute; top: 100%; left: 50%; transform: translateX(-50%);
      margin-top: 8px; background: #1e293b; border: 1px solid #475569;
      border-radius: 12px; padding: 16px; width: 280px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.5); z-index: 50;
    }
    .cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; text-align: center; }
    .cal-grid .day-label { font-size: 11px; color: #64748b; padding: 4px 0; }
    .cal-grid .day {
      font-size: 13px; padding: 6px 0; border-radius: 6px;
      color: #475569; cursor: default; position: relative;
    }
    .cal-grid .day.has-signal { color: #e2e8f0; cursor: pointer; }
    .cal-grid .day.has-signal:hover { background: #334155; }
    .cal-grid .day.has-signal::after {
      content: ''; position: absolute; bottom: 2px; left: 50%;
      transform: translateX(-50%); width: 4px; height: 4px;
      background: #3b82f6; border-radius: 50%;
    }
    .cal-grid .day.selected { background: #3b82f6; color: white; font-weight: 600; }
    .cal-grid .day.selected::after { background: white; }
    .cal-grid .day.today { outline: 2px solid #f59e0b; outline-offset: -2px; }
    .date-nav-btn {
      background: #334155; border: none; color: #94a3b8;
      width: 28px; height: 28px; border-radius: 6px;
      cursor: pointer; font-size: 14px;
      display: flex; align-items: center; justify-content: center;
    }
    .date-nav-btn:hover { background: #475569; color: #e2e8f0; }
    .date-nav-btn:disabled { opacity: 0.3; cursor: default; }
    .date-nav-btn:disabled:hover { background: #334155; color: #94a3b8; }
    .date-display-btn {
      background: #334155; border: none; color: #e2e8f0;
      padding: 4px 12px; border-radius: 6px;
      font-size: 13px; font-weight: 500; cursor: pointer;
    }
    .date-display-btn:hover { background: #475569; }
```

- [ ] **Step 2: Replace signal list header HTML**

Replace the signal list header (lines 84-91 area) from:

```html
      <div class="w-[340px] flex-shrink-0 bg-slate-800 rounded-lg overflow-hidden flex flex-col">
        <div class="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
          <span class="text-sm font-semibold text-slate-300" id="signal-list-title">시그널 목록</span>
          <button onclick="filterSignals('all')" class="text-xs text-slate-500 hover:text-slate-300" id="btn-show-all" style="display:none;">전체보기</button>
        </div>
```

To:

```html
      <div class="w-[340px] flex-shrink-0 bg-slate-800 rounded-lg overflow-hidden flex flex-col">
        <div class="px-4 py-3 border-b border-slate-700">
          <div class="flex items-center justify-between mb-1">
            <span class="text-sm font-semibold text-slate-300" id="signal-list-title">시그널 목록</span>
            <button onclick="filterSignals('all')" class="text-xs text-slate-500 hover:text-slate-300" id="btn-show-all" style="display:none;">전체보기</button>
          </div>
          <div class="flex items-center justify-center gap-2 relative" id="date-nav">
            <button class="date-nav-btn" id="btn-prev-date" onclick="navigateDate(-1)">&#9664;</button>
            <button class="date-display-btn" id="date-display" onclick="toggleCalendar()">--.--(--)</button>
            <button class="date-nav-btn" id="btn-next-date" onclick="navigateDate(1)">&#9654;</button>
            <!-- Calendar popup inserted here by JS -->
          </div>
        </div>
```

- [ ] **Step 3: Verify the page renders without JS errors**

Open http://127.0.0.1:5002/us/dashboard in a browser. The signal list header should now show `시그널 목록` with `◀ --.--(--)  ▶` below it. Buttons won't work yet (JS not implemented).

- [ ] **Step 4: Commit**

```bash
git add web/templates/index.html
git commit -m "feat(ui): add date navigation HTML/CSS to signal list header"
```

---

### Task 5: Frontend — 날짜 선택 JS 로직 구현

**Files:**

- Modify: `web/templates/index.html` (JS section)

- [ ] **Step 1: Add date state variables**

In the JS State section (around line 173), add after `let symbolNames = {};`:

```javascript
    let signalDates = [];       // available signal dates (descending)
    let selectedDate = null;    // currently selected date string (YYYY-MM-DD)
    let calendarOpen = false;
```

- [ ] **Step 2: Add loadSignalDates function**

Add after the `fetchJSON` helper (around line 213):

```javascript
    // -----------------------------------------------------------------------
    // Signal Date Navigation
    // -----------------------------------------------------------------------
    const DAY_NAMES = ['일', '월', '화', '수', '목', '금', '토'];

    function formatDateShort(dateStr) {
      const d = new Date(dateStr + 'T00:00:00');
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      const day = DAY_NAMES[d.getDay()];
      return `${mm}.${dd}(${day})`;
    }

    async function loadSignalDates() {
      try {
        const data = await fetchJSON(`/api/${market}/signals/dates`);
        signalDates = data.dates || [];
      } catch (e) {
        console.error('Failed to load signal dates:', e);
        signalDates = [];
      }
    }

    function initSelectedDate() {
      const stored = localStorage.getItem(`signal_date_${market}`);
      if (stored && signalDates.includes(stored)) {
        selectedDate = stored;
      } else if (signalDates.length > 0) {
        selectedDate = signalDates[0];
      } else {
        selectedDate = null;
      }
      updateDateDisplay();
    }

    function updateDateDisplay() {
      const el = document.getElementById('date-display');
      if (selectedDate) {
        el.textContent = formatDateShort(selectedDate);
      } else {
        el.textContent = '--.--(--)';
      }
      // Update nav button states
      const idx = signalDates.indexOf(selectedDate);
      document.getElementById('btn-prev-date').disabled = (idx < 0 || idx >= signalDates.length - 1);
      document.getElementById('btn-next-date').disabled = (idx <= 0);
    }

    function navigateDate(direction) {
      if (!selectedDate || !signalDates.length) return;
      const idx = signalDates.indexOf(selectedDate);
      if (idx < 0) return;
      // direction: -1 = older (higher index), +1 = newer (lower index)
      const newIdx = idx - direction;
      if (newIdx >= 0 && newIdx < signalDates.length) {
        selectDate(signalDates[newIdx]);
      }
    }

    function selectDate(dateStr) {
      selectedDate = dateStr;
      localStorage.setItem(`signal_date_${market}`, dateStr);
      updateDateDisplay();
      closeCalendar();
      loadSignals();
      loadSummary();
    }
```

- [ ] **Step 3: Add calendar popup functions**

Add immediately after the `selectDate` function:

```javascript
    function toggleCalendar() {
      if (calendarOpen) { closeCalendar(); } else { openCalendar(); }
    }

    function closeCalendar() {
      calendarOpen = false;
      const existing = document.getElementById('cal-popup');
      if (existing) existing.remove();
      const overlay = document.getElementById('cal-overlay');
      if (overlay) overlay.remove();
    }

    function openCalendar() {
      closeCalendar();
      calendarOpen = true;

      // Overlay to catch outside clicks
      const overlay = document.createElement('div');
      overlay.id = 'cal-overlay';
      overlay.className = 'cal-overlay';
      overlay.onclick = closeCalendar;
      document.body.appendChild(overlay);

      const popup = document.createElement('div');
      popup.id = 'cal-popup';
      popup.className = 'cal-popup';

      const refDate = selectedDate ? new Date(selectedDate + 'T00:00:00') : new Date();
      renderCalendarMonth(popup, refDate.getFullYear(), refDate.getMonth());

      document.getElementById('date-nav').appendChild(popup);
    }

    function renderCalendarMonth(popup, year, month) {
      const today = new Date();
      const todayStr = today.toISOString().slice(0, 10);

      // Header
      const header = document.createElement('div');
      header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;';

      const prevBtn = document.createElement('button');
      prevBtn.textContent = '◀';
      prevBtn.style.cssText = 'background:none;border:none;color:#94a3b8;cursor:pointer;font-size:14px;padding:4px;';
      prevBtn.onclick = (e) => { e.stopPropagation(); const m = month === 0 ? 11 : month - 1; const y = month === 0 ? year - 1 : year; popup.innerHTML = ''; renderCalendarMonth(popup, y, m); };

      const title = document.createElement('span');
      title.style.cssText = 'font-size:14px;font-weight:600;';
      title.textContent = `${year}년 ${month + 1}월`;

      const nextBtn = document.createElement('button');
      nextBtn.textContent = '▶';
      nextBtn.style.cssText = 'background:none;border:none;color:#94a3b8;cursor:pointer;font-size:14px;padding:4px;';
      nextBtn.onclick = (e) => { e.stopPropagation(); const m = month === 11 ? 0 : month + 1; const y = month === 11 ? year + 1 : year; popup.innerHTML = ''; renderCalendarMonth(popup, y, m); };

      header.append(prevBtn, title, nextBtn);
      popup.appendChild(header);

      // Grid
      const grid = document.createElement('div');
      grid.className = 'cal-grid';

      // Day labels (Mon-Sun)
      ['월','화','수','목','금','토','일'].forEach(d => {
        const label = document.createElement('div');
        label.className = 'day-label';
        label.textContent = d;
        grid.appendChild(label);
      });

      // First day of month (0=Sun, adjust to Mon-start)
      const firstDay = new Date(year, month, 1).getDay();
      const startOffset = firstDay === 0 ? 6 : firstDay - 1;
      const daysInMonth = new Date(year, month + 1, 0).getDate();

      // Empty cells before first day
      for (let i = 0; i < startOffset; i++) {
        const empty = document.createElement('div');
        empty.className = 'day';
        grid.appendChild(empty);
      }

      // Day cells
      for (let d = 1; d <= daysInMonth; d++) {
        const cell = document.createElement('div');
        cell.className = 'day';
        cell.textContent = d;

        const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

        if (signalDates.includes(dateStr)) {
          cell.classList.add('has-signal');
          cell.onclick = (e) => { e.stopPropagation(); selectDate(dateStr); };
        }
        if (dateStr === selectedDate) cell.classList.add('selected');
        if (dateStr === todayStr) cell.classList.add('today');

        grid.appendChild(cell);
      }

      popup.appendChild(grid);
    }
```

- [ ] **Step 4: Modify loadSignals to use selected date**

Replace the existing `loadSignals` function (around line 270):

```javascript
    async function loadSignals() {
      try {
        const dateParam = selectedDate ? `?date=${selectedDate}` : '';
        allSignals = await fetchJSON(`/api/${market}/signals${dateParam}`);
        renderSignalList(allSignals);
      } catch (e) {
        console.error('Failed to load signals:', e);
      }
    }
```

- [ ] **Step 5: Modify loadSummary to use selected date**

Replace the existing `loadSummary` function (around line 253):

```javascript
    async function loadSummary() {
      try {
        const dateParam = selectedDate ? `?date=${selectedDate}` : '';
        const data = await fetchJSON(`/api/${market}/signals/summary${dateParam}`);
        document.getElementById('count-buy').textContent = data.buy || 0;
        document.getElementById('count-sell').textContent = data.sell || 0;
        document.getElementById('count-watch').textContent = data.watch || 0;
      } catch (e) {
        console.error('Failed to load summary:', e);
      }
    }
```

- [ ] **Step 6: Update the init sequence**

Replace the Init section at the bottom of the script (around line 664):

```javascript
    // -----------------------------------------------------------------------
    // Init
    // -----------------------------------------------------------------------
    updateMarketButtons();
    loadSymbolNames().then(async () => {
      loadIndices();
      await loadSignalDates();
      initSelectedDate();
      loadSummary();
      loadSignals();
    });
```

- [ ] **Step 7: Manual smoke test**

Open http://127.0.0.1:5002/us/dashboard:

1. Signal list header shows the latest signal date (e.g., `04.06(월)`)
2. Click date → calendar popup opens, signal dates have blue dots
3. Click a date with blue dot → signals reload for that date, summary updates
4. ◀ ▶ buttons navigate to prev/next signal date
5. Switch to KR (`/kr/dashboard`) → back to US → selected date is remembered
6. Refresh page → selected date persists from localStorage

- [ ] **Step 8: Commit**

```bash
git add web/templates/index.html
git commit -m "feat(ui): implement date navigation and calendar popup for signals"
```

---

### Task 6: Final integration test and cleanup

**Files:**

- Modify: `tests/test_web_api.py` (integration test 추가)
- Modify: `web/app.py` (docstring 업데이트)

- [ ] **Step 1: Add integration test for full flow**

Append to `tests/test_web_api.py`:

```python
class TestDateFilterIntegration:
    def test_dates_and_signals_consistent(self, client):
        """Signals returned for a date should match that date in dates list."""
        dates_resp = client.get("/api/us/signals/dates")
        dates = dates_resp.get_json()["dates"]

        for d in dates:
            signals_resp = client.get(f"/api/us/signals?date={d}")
            signals = signals_resp.get_json()
            assert len(signals) > 0, f"Date {d} in dates list but no signals"
            assert all(s["date"] == d for s in signals)

    def test_summary_matches_signals(self, client):
        """Summary counts should match actual signal counts."""
        for d in ["2026-04-06", "2026-04-03"]:
            signals = client.get(f"/api/us/signals?date={d}").get_json()
            summary = client.get(f"/api/us/signals/summary?date={d}").get_json()

            actual = {"buy": 0, "sell": 0, "watch": 0}
            for s in signals:
                if s["signal_type"] in actual:
                    actual[s["signal_type"]] += 1
            assert summary == actual
```

- [ ] **Step 2: Run full test suite**

Run: `PYTHONPATH=. python3 -m pytest tests/test_web_api.py -v`

Expected: All tests PASS (12 total).

- [ ] **Step 3: Update app.py module docstring**

Replace the module docstring at the top of `web/app.py` (lines 1-12):

```python
"""Flask web application with API endpoints for the Trend Trading dashboard.

Routes:
    GET /                              → redirect to /kr/dashboard
    GET /<market>/dashboard            → render index.html
    GET /<market>/performance          → render performance.html
    GET /api/<market>/indices          → market indices for today
    GET /api/<market>/signals          → signals for a date (?date=YYYY-MM-DD)
    GET /api/<market>/signals/dates    → list of dates with signals (90 days)
    GET /api/<market>/signals/summary  → buy/sell/watch counts (?date=YYYY-MM-DD)
    GET /api/<market>/chart/<symbol>   → OHLCV + Livermore states
    GET /api/<market>/performance      → trade stats and signal accuracy
"""
```

- [ ] **Step 4: Run existing tests to ensure no regression**

Run: `PYTHONPATH=. python3 -m pytest tests/ -v`

Expected: All existing tests + new tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_web_api.py web/app.py
git commit -m "test: add integration tests and update docstring for date filter"
```
