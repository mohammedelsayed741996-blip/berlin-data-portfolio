// Front end for the HR policy assistant: ask a question, read the answer with its sources, rate it.
// Plain TypeScript, no framework, compiled with tsc to web/dist/app.js.

type Citation = { n: number; pid: string; policy_id: string; title: string; section: string; version: string; effective_date: string };
type AskResponse = {
  answer: string; citations: Citation[]; answered: boolean; confidence: number; engine: string;
  latency_ms: number; role: string; redacted: string[]; query_id?: number; error?: string;
};

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;

function sessionId(): string {
  // random per-tab token, no personal data; kept only in memory
  const w = window as unknown as { __sid?: string };
  if (!w.__sid) w.__sid = Math.random().toString(36).slice(2) + Date.now().toString(36);
  return w.__sid;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
}

function renderAnswer(r: AskResponse): void {
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
  box.querySelectorAll<HTMLButtonElement>(".rate button").forEach((b) =>
    b.addEventListener("click", async () => {
      await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query_id: r.query_id, helpful: b.dataset.h === "1" }) });
      const rate = box.querySelector(".rate");
      if (rate) rate.textContent = "Thanks for the feedback.";
    }));
}

async function ask(question: string): Promise<void> {
  const btn = $<HTMLButtonElement>("ask");
  btn.disabled = true;
  btn.textContent = "Searching…";
  try {
    const res = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, role: $<HTMLSelectElement>("role").value, session: sessionId() }) });
    const data = (await res.json()) as AskResponse;
    if (!res.ok) throw new Error(data.error || res.statusText);
    renderAnswer(data);
  } catch (e) {
    const box = $("answer");
    box.hidden = false;
    box.className = "card declined";
    box.textContent = `Something went wrong: ${(e as Error).message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Ask";
  }
}

function init(): void {
  $("form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const q = $<HTMLInputElement>("q").value.trim();
    if (q) void ask(q);
  });
  document.querySelectorAll<HTMLButtonElement>(".example").forEach((b) =>
    b.addEventListener("click", () => {
      $<HTMLInputElement>("q").value = b.textContent || "";
      void ask(b.textContent || "");
    }));
  void fetch("/health").then((r) => r.json()).then((h: { demo_mode: boolean }) => {
    $("role-wrap").hidden = !h.demo_mode;
  });
}

document.addEventListener("DOMContentLoaded", init);
