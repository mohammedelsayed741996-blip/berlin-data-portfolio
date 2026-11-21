"use strict";
// Front end for the HR policy assistant: ask a question, read the answer with its sources, rate it.
// Plain TypeScript, no framework, compiled with tsc to web/dist/app.js.
const $ = (id) => document.getElementById(id);
function sessionId() {
    // random per-tab token, no personal data; kept only in memory
    const w = window;
    if (!w.__sid)
        w.__sid = Math.random().toString(36).slice(2) + Date.now().toString(36);
    return w.__sid;
}
function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function renderAnswer(r) {
    const box = $("answer");
    box.hidden = false;
    box.className = r.answered ? "card answered" : "card declined";
    const text = escapeHtml(r.answer).replace(/\[(\d+)\]/g, '<sup class="ref">[$1]</sup>');
    const sources = r.citations
        .map((c) => `<li><span class="ref">[${c.n}]</span> ${escapeHtml(c.policy_id)} · ${escapeHtml(c.title)}, “${escapeHtml(c.section)}” <span class="muted">v${escapeHtml(c.version)}, valid from ${escapeHtml(c.effective_date)}</span></li>`)
        .join("");
    const note = r.redacted.length ? `<p class="note">Personal data removed before processing: ${r.redacted.join(", ").toLowerCase()}.</p>` : "";
    box.innerHTML = `<p class="text">${text}</p>${sources ? `<ul class="sources">${sources}</ul>` : ""}${note}
    <div class="meta"><span>${r.engine} · ${r.latency_ms.toFixed(0)} ms · confidence ${r.confidence.toFixed(2)} · role ${escapeHtml(r.role)}</span>
    ${r.query_id !== undefined ? `<span class="rate">Helpful? <button data-h="1">Yes</button><button data-h="0">No</button></span>` : ""}</div>`;
    box.querySelectorAll(".rate button").forEach((b) => b.addEventListener("click", async () => {
        await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query_id: r.query_id, helpful: b.dataset.h === "1" }) });
        const rate = box.querySelector(".rate");
        if (rate)
            rate.textContent = "Thanks for the feedback.";
    }));
}
async function ask(question) {
    const btn = $("ask");
    btn.disabled = true;
    btn.textContent = "Searching…";
    try {
        const res = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, role: $("role").value, session: sessionId() }) });
        const data = (await res.json());
        if (!res.ok)
            throw new Error(data.error || res.statusText);
        renderAnswer(data);
    }
    catch (e) {
        const box = $("answer");
        box.hidden = false;
        box.className = "card declined";
        box.textContent = `Something went wrong: ${e.message}`;
    }
    finally {
        btn.disabled = false;
        btn.textContent = "Ask";
    }
}
function init() {
    $("form").addEventListener("submit", (ev) => {
        ev.preventDefault();
        const q = $("q").value.trim();
        if (q)
            void ask(q);
    });
    document.querySelectorAll(".example").forEach((b) => b.addEventListener("click", () => {
        $("q").value = b.textContent || "";
        void ask(b.textContent || "");
    }));
    void fetch("/health").then((r) => r.json()).then((h) => {
        $("role-wrap").hidden = !h.demo_mode;
    });
}
document.addEventListener("DOMContentLoaded", init);
