// Exercises the bridge's handshake ownership rules without VS Code.
//
// The bug this guards against: every VS Code window loads the extension, only
// one can hold the port, and the ones that cannot used to delete the winner's
// handshake on shutdown, silently killing a working bridge.

const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const http = require("node:http");
const Module = require("node:module");

// The extension requires "vscode", which only exists inside the editor.
// Port 0 takes a free one, so the check never fights the real bridge. Tests
// that need a specific port set this.
let configuredPort = 0;
const BUSY_PORT = 8791;

const commands = new Map();

const stub = {
  window: {
    createOutputChannel: () => ({ appendLine() {}, show() {}, dispose() {} }),
    createStatusBarItem: () => ({ show() {}, dispose() {} }),
    showErrorMessage: () => ({ then: (fn) => fn(undefined) }),
    showWarningMessage() {},
    showInformationMessage: async () => undefined,
  },
  workspace: {
    getConfiguration: () => ({
      get: (key) => (key === "port" ? configuredPort : undefined),
    }),
  },
  commands: {
    registerCommand: (id, handler) => {
      commands.set(id, handler);
      return { dispose: () => commands.delete(id) };
    },
    executeCommand: (id, ...args) => commands.get(id)?.(...args),
  },
  StatusBarAlignment: { Right: 2 },
  ThemeColor: class {},
  CancellationTokenSource: class {
    constructor() {
      this.token = {};
    }
    dispose() {}
  },
  LanguageModelChatMessage: { User: (t) => t },
  lm: { selectChatModels: async () => [] },
  version: "test",
};
const vscode = stub;

const load = Module._load;
Module._load = (request, ...rest) => (request === "vscode" ? stub : load(request, ...rest));

const HANDSHAKE = path.join(os.homedir(), ".joblookup", "bridge.json");

function backup() {
  return fs.existsSync(HANDSHAKE) ? fs.readFileSync(HANDSHAKE) : null;
}

function restore(saved) {
  if (saved) fs.writeFileSync(HANDSHAKE, saved);
  else if (fs.existsSync(HANDSHAKE)) fs.unlinkSync(HANDSHAKE);
}

function readHandshake() {
  try {
    return JSON.parse(fs.readFileSync(HANDSHAKE, "utf8"));
  } catch {
    return null;
  }
}

function write(pid) {
  fs.mkdirSync(path.dirname(HANDSHAKE), { recursive: true });
  fs.writeFileSync(
    HANDSHAKE,
    JSON.stringify({ base_url: "http://127.0.0.1:8771", token: "x", pid })
  );
}

const results = [];
function check(name, fn) {
  try {
    fn();
    results.push(`  PASS  ${name}`);
  } catch (error) {
    results.push(`  FAIL  ${name}\n        ${error.message}`);
    process.exitCode = 1;
  }
}

async function checkAsync(name, fn) {
  try {
    await fn();
    results.push(`  PASS  ${name}`);
  } catch (error) {
    results.push(`  FAIL  ${name}\n        ${error.message}`);
    process.exitCode = 1;
  }
}

function get(url, token, agent) {
  return new Promise((resolve, reject) => {
    const request = http.get(
      url,
      { headers: token ? { authorization: `Bearer ${token}` } : {}, agent },
      (response) => {
        let body = "";
        response.on("data", (chunk) => (body += chunk));
        response.on("end", () => resolve({ status: response.statusCode, body }));
      }
    );
    request.on("error", reject);
    request.setTimeout(3000, () => request.destroy(new Error("timed out")));
  });
}

async function main() {
  const saved = backup();
  try {
    const bridge = require(path.join(__dirname, "..", "vscode-bridge", "extension.js"));
    assert(typeof bridge.activate === "function", "activate must be exported");
    assert(typeof bridge.deactivate === "function", "deactivate must be exported");

    const source = fs
      .readFileSync(path.join(__dirname, "..", "vscode-bridge", "extension.js"), "utf8")
      .replace(/\r\n/g, "\n");

    check("a handshake owned by another live process is never deleted", () => {
      // A pid that certainly exists and is not us.
      write(process.ppid || 4);
      // deactivate() is what runs when a window closes or reloads.
      bridge.deactivate();
      assert(fs.existsSync(HANDSHAKE), "another window's handshake was deleted");
    });

    check("a handshake we own is cleaned up on shutdown", () => {
      write(process.pid);
      bridge.deactivate();
      assert(!fs.existsSync(HANDSHAKE), "our own stale handshake was left behind");
    });

    check("only the owning pid may remove the handshake", () => {
      assert(
        /existing\.pid !== process\.pid && isAlive\(existing\.pid\)/.test(source),
        "removeHandshake must protect a live foreign owner and only that"
      );
      // The pid guard is the whole protection, so nothing may short-circuit it.
      assert(
        /\n  removeHandshake\(\);/.test(source),
        "stopServer must call removeHandshake unconditionally and let the pid guard decide"
      );
    });

    check("only a live foreign owner is protected", () => {
      // A handshake naming a pid that no longer exists is stale, and holding on
      // to it would point JobLookup at a bridge that is not there.
      write(999_999_999);
      bridge.deactivate();
      assert(!fs.existsSync(HANDSHAKE), "a dead owner's handshake was kept");
    });

    check("a failed bind never becomes the live server", () => {
      // Assigned in the listen callback and nowhere else, so a server that did
      // not bind cannot be mistaken for the running one.
      assert(
        /candidate\.listen\(port, "127\.0\.0\.1", \(\) => \{\n      server = candidate;/.test(source),
        "server must only be assigned once listening has succeeded"
      );
      assert(
        !/\n    server = http\.createServer/.test(source),
        "a server is assigned before it has bound"
      );
    });

    check("the handshake is rewritten if it goes missing while serving", () => {
      assert(/watchdog = setInterval\(ensureHandshake/.test(source));
    });

    check("a port clash stands down instead of raising a dialog", () => {
      assert(/error\.code === "STANDBY"/.test(source));
      assert(/retry = setInterval/.test(source), "no retry, so a closed host never hands over");
    });

    check("a busy port falls back to a free one", () => {
      // Standing down forever would be wrong when the holder is not our bridge.
      assert(/port = await listenOn\(0\);/.test(source), "no fallback to a free port");
    });

    check("closing waits for keep-alive connections to be cut", () => {
      // JobLookup polls /health on a keep-alive socket, so close() alone never
      // completes and the immediate rebind reports EADDRINUSE.
      assert(/closeAllConnections\?\.\(\)/.test(source), "keep-alive sockets are never cut");
      assert(/await stopServer\(\);/.test(source), "restart does not wait for the close");
    });

    check("hosting is claimed exclusively", () => {
      assert(/flag: "wx"/.test(source), "two windows could both claim to host");
    });

    check("timers are torn down with the server", () => {
      // A watchdog left running after shutdown would rewrite a handshake for a
      // server that is no longer listening.
      assert(/async function stopServer\(\) \{\n  clearTimers\(\);/.test(source));
    });

    // --- live activation ---------------------------------------------------
    const subscriptions = [];
    await bridge.activate({ subscriptions });

    await checkAsync("activation writes a handshake JobLookup can read", async () => {
      const shake = readHandshake();
      assert(shake, "no handshake was written");
      assert(shake.pid === process.pid, "handshake does not name this process");
      assert(/^http:\/\/127\.0\.0\.1:\d+$/.test(shake.base_url), "bad base_url");
      assert(shake.token && shake.token.length >= 32, "token missing or too short");
    });

    await checkAsync("the health endpoint answers with the handshake token", async () => {
      const shake = readHandshake();
      const response = await get(`${shake.base_url}/health`, shake.token);
      assert.strictEqual(response.status, 200, `health returned ${response.status}`);
      const payload = JSON.parse(response.body);
      assert.strictEqual(payload.ok, true);
      assert("models" in payload, "health payload has no models list");
    });

    await checkAsync("an unauthenticated caller is refused", async () => {
      const shake = readHandshake();
      const response = await get(`${shake.base_url}/health`, "");
      assert.strictEqual(response.status, 401, `expected 401, got ${response.status}`);
    });

    await checkAsync("a wrong token is refused", async () => {
      const shake = readHandshake();
      const response = await get(`${shake.base_url}/health`, "0".repeat(64));
      assert.strictEqual(response.status, 401, `expected 401, got ${response.status}`);
    });

    await checkAsync("the watchdog puts the handshake back if it is deleted", async () => {
      fs.unlinkSync(HANDSHAKE);
      assert(!fs.existsSync(HANDSHAKE));
      // The extension re-checks every 10 seconds while it is serving.
      await new Promise((resolve) => setTimeout(resolve, 11_000));
      assert(fs.existsSync(HANDSHAKE), "the watchdog did not restore the handshake");
    });

    await checkAsync("shutting down releases the port and clears the handshake", async () => {
      const shake = readHandshake();
      await bridge.deactivate();
      assert(!fs.existsSync(HANDSHAKE), "handshake survived shutdown");
      await assert.rejects(() => get(`${shake.base_url}/health`, shake.token));
    });

    // The failure that started this: a restart while JobLookup was polling
    // /health on a keep-alive socket left close() hanging, so the immediate
    // rebind hit EADDRINUSE and the user got an error dialog.
    await checkAsync("restarting works while a client is holding a connection", async () => {
      await bridge.activate({ subscriptions: [] });
      const first = readHandshake();
      assert(first, "did not start");

      const agent = new http.Agent({ keepAlive: true });
      const held = await get(`${first.base_url}/health`, first.token, agent);
      assert.strictEqual(held.status, 200);

      await vscode.commands.executeCommand("joblookupBridge.restart");

      const second = readHandshake();
      assert(second, "the restart left no handshake");
      assert(second.token !== first.token, "the token was not regenerated");
      const after = await get(`${second.base_url}/health`, second.token);
      assert.strictEqual(after.status, 200, "the bridge did not come back");
      agent.destroy();
      await bridge.deactivate();
    });

    await checkAsync("a port held by something else is worked around", async () => {
      // Occupy the configured port with a stranger, the way another program on
      // the machine would.
      const squatter = http.createServer(() => {});
      await new Promise((resolve) => squatter.listen(BUSY_PORT, "127.0.0.1", resolve));
      configuredPort = BUSY_PORT;
      try {
        await bridge.activate({ subscriptions: [] });
        const shake = readHandshake();
        assert(shake, "the bridge gave up instead of finding a free port");
        const port = Number(new URL(shake.base_url).port);
        assert.notStrictEqual(port, BUSY_PORT, "it claimed a port it does not hold");
        const response = await get(`${shake.base_url}/health`, shake.token);
        assert.strictEqual(response.status, 200, "the fallback port does not serve");
      } finally {
        await bridge.deactivate();
        squatter.close();
        configuredPort = 0;
      }
    });
  } finally {
    restore(saved);
  }

  console.log(results.join("\n"));
  console.log(process.exitCode ? "\nFAILED" : "\nAll bridge lifecycle checks passed.");
}

void main();
