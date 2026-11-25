// Isolated rendering of development sources with synthetic data, never live HA.
// Requires Chromium and Node's built-in WebSocket; no npm packages or auth.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";

const frontend = new URL("../../custom_components/contraction_tracker/frontend/", import.meta.url);
const cache = process.env.SUPPORT_PREVIEW_DIR ||
  (existsSync("/data/v2/cache/opencode") ? "/data/v2/cache/opencode" : tmpdir());
const output = await mkdtemp(resolve(cache, "contraction-support-preview-"));
const files = new Set(["tracker.js", "state.js", "transport.js", "tracker.css"]);
const fixture = `<!doctype html><html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Synthetic support-footer preview</title>
<style>body{margin:0;padding:8px;background:var(--primary-background-color);color:var(--primary-text-color)}#mount{max-width:560px;margin:auto}</style>
</head><body><div id="mount"></div><script>
window.ready=(async()=>{
  const params=new URLSearchParams(location.search),mode=params.get("mode");
  const light=params.get("theme")==="light";
  document.documentElement.style.setProperty("--primary-background-color",light?"#fafafa":"#111111");
  document.documentElement.style.setProperty("--primary-text-color",light?"#212121":"#eeeeee");
  document.documentElement.style.colorScheme=light?"light":"dark";
  await import("/frontend/tracker.js?ui=support-footer1");
  const now=Math.floor(Date.now()/1000);
  const current={p:"rest",s:now-60,e:now-15,n:1,d:45,i:0,r:0,v:"Mild",
    k:"synthetic-revision",recent:[],movement:{k:"synthetic-movement",count:0,last:0},
    hourly:{count:1,completed:1,duration:45,interval:null},
    guidance:{mode:"manual",location:"unspecified",interval:300,k:"synthetic-settings"}};
  window.commands=[];
  const hass={states:{"sensor.synthetic_session":{entity_id:"sensor.synthetic_session",state:"rest",
    attributes:{contraction_tracker:true,entry_id:"synthetic-entry",notifications_enabled:true,current}},
    "input_text.synthetic":{state:JSON.stringify(current),attributes:{}}},
    connection:{connected:params.get("online")==="true"},
    callService:async(...args)=>window.commands.push(args),
    callWS:async()=>({items:[]})};
  let root;
  if(mode==="panel"){
    const panel=document.createElement("contraction-tracker-panel");
    panel.panel={config:{entry_id:"synthetic-entry"}};
    panel.hass=hass;document.querySelector("#mount").append(panel);
    root=panel.shadowRoot.querySelector("contraction-tracker-app-card");
  }else{
    root=document.createElement("contraction-tracker-app-card");
    root.setConfig(mode==="legacy"?{legacy:{entity:"input_text.synthetic"}}:{entry_id:"synthetic-entry"});
    root.preview=mode==="preview";root.hass=hass;
    document.querySelector("#mount").append(root);
  }
  window.card=root;
  // The component can re-render after its synthetic history response.
  await Promise.resolve();await Promise.resolve();
  const link=root.shadowRoot.querySelector('link[rel="stylesheet"]');
  if(!link.sheet)await new Promise((done,fail)=>{link.onload=done;link.onerror=fail;});
  await new Promise(done=>requestAnimationFrame(()=>requestAnimationFrame(done)));
  return true;
})();
</script></body></html>`;

const server = createServer(async (request, response) => {
  const url = new URL(request.url, "http://127.0.0.1");
  if (url.pathname === "/preview") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" });
    response.end(fixture);
  } else if (url.pathname.startsWith("/frontend/") && files.has(url.pathname.slice(10))) {
    const name = url.pathname.slice(10);
    response.writeHead(200, { "Content-Type": name.endsWith(".css") ? "text/css; charset=utf-8" : "text/javascript; charset=utf-8" });
    response.end(await readFile(new URL(name, frontend)));
  } else {
    response.writeHead(404); response.end();
  }
});
server.listen(0, "127.0.0.1");
await once(server, "listening");
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = spawn(process.env.CHROMIUM || "/usr/bin/chromium", [
  "--headless", "--no-sandbox", "--disable-gpu", "--disable-background-networking",
  "--no-first-run", "--no-default-browser-check", "--remote-debugging-port=0",
  "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
  `--user-data-dir=${resolve(output, "browser-profile")}`, "about:blank",
], { stdio: ["ignore", "ignore", "pipe"] });
let socket;
try {
  const endpoint = await new Promise((done, fail) => {
    const timeout = setTimeout(() => fail(new Error("Chromium startup timed out")), 15000);
    const output = (chunk) => {
      const match = chunk.toString().match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timeout); browser.stderr.off("data", output); done(match[1]); }
    };
    browser.stderr.on("data", output);
    browser.once("error", fail);
    browser.once("exit", (code) => fail(new Error(`Chromium exited early: ${code}`)));
  });
  socket = new WebSocket(endpoint);
  await once(socket, "open");
  let id = 0;
  const pending = new Map(), events = new Set();
  socket.addEventListener("message", ({ data }) => {
    const message = JSON.parse(data);
    if (message.id) {
      const item = pending.get(message.id);
      if (!item) return;
      clearTimeout(item.timer); pending.delete(message.id);
      if (message.error) item.fail(new Error(JSON.stringify(message.error)));
      else item.done(message.result);
    } else {
      for (const listener of events) listener(message);
    }
  });
  const send = (method, params = {}, sessionId) => new Promise((done, fail) => {
    const key = ++id;
    const timer = setTimeout(() => {
      pending.delete(key); fail(new Error(`CDP timeout: ${method}`));
    }, 15000);
    pending.set(key, { done, fail, timer });
    socket.send(JSON.stringify({ id: key, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  const { targetId } = await send("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
  const call = (method, params) => send(method, params, sessionId);
  const evaluate = async (expression) => {
    const result = await call("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await call("Page.enable");
  await call("Runtime.enable");
  await call("Network.enable");
  const requests = [], errors = [];
  events.add((message) => {
    if (message.sessionId !== sessionId) return;
    if (message.method === "Network.requestWillBeSent") requests.push(message.params.request.url);
    if (message.method === "Runtime.exceptionThrown") errors.push(message.params.exceptionDetails);
  });
  const results = [];
  for (const width of [320, 430, 1280]) {
    for (const theme of ["light", "dark"]) {
      for (const mode of ["card", "panel", "legacy", "preview"]) {
        for (const online of [true, false]) {
          await call("Emulation.setDeviceMetricsOverride", {
            width, height: 950, deviceScaleFactor: 1, mobile: width < 600,
          });
          const loaded = new Promise((done) => {
            const listener = (message) => {
              if (message.sessionId === sessionId && message.method === "Page.loadEventFired") {
                events.delete(listener); done();
              }
            };
            events.add(listener);
          });
          await call("Page.navigate", { url: `${origin}/preview?mode=${mode}&theme=${theme}&online=${online}` });
          await loaded;
          await evaluate("window.ready");
          const data = await evaluate(`(()=>{
            const root=window.card.shadowRoot, section=root.querySelector(".support"), link=root.querySelector(".support-link");
            section.scrollIntoView({block:"center"});
            const rect=link.getBoundingClientRect(), box=section.getBoundingClientRect();
            const footer=root.querySelector(".footer").getBoundingClientRect();
            const luminance=color=>{
              const channels=color.match(/[\\d.]+/g).slice(0,3).map(Number).map(channel=>{
                const value=channel/255;return value<=.04045?value/12.92:((value+.055)/1.055)**2.4;
              });
              return channels[0]*.2126+channels[1]*.7152+channels[2]*.0722;
            };
            const backgrounds=getComputedStyle(root.querySelector(".app")).backgroundImage.match(/rgba?\\([^)]+\\)/g);
            const contrast=color=>Math.min(...backgrounds.map(background=>{
              const a=luminance(color),b=luminance(background);
              return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
            }));
            return {count:root.querySelectorAll(".support").length,href:link.href,
              target:link.target,rel:link.rel,referrer:link.referrerPolicy,
              position:getComputedStyle(section).position,touchHeight:rect.height,
              overflow:document.documentElement.scrollWidth>innerWidth,
              linkFits:link.scrollWidth<=link.clientWidth+1&&rect.right<=box.right+1&&rect.left>=box.left-1,
              belowControls:box.top>=footer.bottom,disabled:link.hasAttribute("disabled"),
              textContrast:contrast(getComputedStyle(section).color),
              linkContrast:contrast(getComputedStyle(link).color),
              commands:window.commands.length};
          })()`);
          assert.equal(data.count, 1);
          assert.equal(data.href, "https://buymeacoffee.com/Badger182");
          assert.equal(data.target, "_blank");
          assert.equal(data.rel, "noopener noreferrer");
          assert.equal(data.referrer, "no-referrer");
          assert.equal(data.position, "static");
          assert.ok(data.touchHeight >= 44 && data.linkFits && data.belowControls);
          assert.equal(data.overflow, false);
          assert.equal(data.disabled, false);
          assert.ok(data.textContrast >= 4.5 && data.linkContrast >= 4.5);
          assert.equal(data.commands, 0);
          // Exercise native keyboard activation but prevent payment-site navigation
          // in this disposable fixture. The production link has no click handler.
          await evaluate(`(()=>{
            const link=window.card.shadowRoot.querySelector(".support-link");
            window.linkClick=null;
            link.addEventListener("click",event=>{
              window.linkClick={trusted:event.isTrusted,preventedBeforeTest:event.defaultPrevented};
              event.preventDefault();
            },{once:true});
            link.focus();return true;
          })()`);
          await call("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
          await call("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
          const activated = await evaluate("({click:window.linkClick,commands:window.commands.length,focused:window.card.shadowRoot.activeElement?.className})");
          assert.deepEqual(activated.click, { trusted: true, preventedBeforeTest: false });
          assert.equal(activated.commands, 0);
          assert.equal(activated.focused, "support-link");
          if (mode === "card" && online && width !== 430) {
            const screenshot = await call("Page.captureScreenshot", { format: "png" });
            await writeFile(resolve(output, `support-${width}-${theme}.png`), Buffer.from(screenshot.data, "base64"));
          }
          results.push({ width, theme, mode, online, ...data });
        }
      }
    }
  }
  assert.deepEqual(errors, []);
  assert.ok(requests.every(url => url.startsWith(origin + "/")), "Unexpected non-local request");
  await writeFile(resolve(output, "results.json"), JSON.stringify({ results, requests }, null, 2) + "\n");
  console.log(`Passed ${results.length} real-browser layout/keyboard/privacy cases. No external requests or tracker commands.`);
  console.log(`Synthetic preview screenshots and results: ${output}`);
} finally {
  socket?.close();
  browser.kill("SIGTERM");
  server.close();
}
