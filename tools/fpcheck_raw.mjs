// Open a URL in the CDP Chromium WITHOUT any automation client attached during load
// (Target.createTarget via HTTP), wait, then attach briefly only to screenshot + read text.
// Usage: node fpcheck_raw.mjs <url> <outdir> [waitSec]
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const [url, outdir, waitArg] = process.argv.slice(2);
const waitSec = Number(waitArg || 25);
const cdp = process.env.CHATGPT_CDP_URL || "http://127.0.0.1:9222";
mkdirSync(outdir, { recursive: true });

const created = await (await fetch(`${cdp}/json/new?${encodeURIComponent(url)}`, { method: "PUT" })).json();
console.error("opened", created.id, url);
await new Promise(r => setTimeout(r, waitSec * 1000));

const ws = new WebSocket(created.webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r);
let id = 0;
const pending = new Map();
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } };
const send = (method, params = {}) => new Promise(res => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });

const text = await send("Runtime.evaluate", { expression: "document.body ? document.body.innerText : ''", returnByValue: true });
const shot = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
writeFileSync(join(outdir, "page.txt"), text.result?.result?.value ?? JSON.stringify(text));
writeFileSync(join(outdir, "shot.png"), Buffer.from(shot.result?.data ?? "", "base64"));
ws.close();
await fetch(`${cdp}/json/close/${created.id}`);
console.log(JSON.stringify({ mode: "raw", url, outdir, chars: (text.result?.result?.value ?? "").length }));
