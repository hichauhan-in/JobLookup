const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const http = require('node:http');
const { createBridge } = require('../bridge.cjs');

async function setup(testContext, options = {}) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'joblookup-bridge-test-'));
  const commands = new Map();
  const state = { calls: 0, cancelled: false, permission: options.permission ?? true };
  const model = {
    id: 'test-model', family: 'test-model', name: 'Test model', maxInputTokens: 10000,
    countTokens: async (text) => text.length / 4,
    sendRequest: async (_messages, _options, token) => {
      state.calls += 1;
      assert.equal(token.isCancellationRequested, false);
      return { text: (async function* () { yield 'ready'; })() };
    },
  };
  const vscode = {
    workspace: { getConfiguration: () => ({ get: (key) => key === 'port' ? options.port ?? 0 : undefined }) },
    window: {
      createOutputChannel: () => ({ appendLine() {}, show() {}, dispose() {} }),
      createStatusBarItem: () => ({ show() {}, dispose() {} }),
      showErrorMessage: async (message) => { throw new Error(message); },
      showInformationMessage: async () => undefined,
    },
    commands: { registerCommand: (name, command) => { commands.set(name, command); return { dispose() {} }; } },
    StatusBarAlignment: { Right: 2 },
    LanguageModelChatMessage: { User: (content) => ({ role: 'user', content }), Assistant: (content) => ({ role: 'assistant', content }) },
    CancellationTokenSource: class {
      token = { isCancellationRequested: false };
      cancel() { this.token.isCancellationRequested = true; state.cancelled = true; }
      dispose() {}
    },
    lm: { selectChatModels: async () => [model] },
  };
  const bridge = createBridge(vscode, directory);
  const context = { subscriptions: [], languageModelAccessInformation: { canSendRequest: () => state.permission } };
  testContext.after(async () => { await bridge.deactivate(); fs.rmSync(directory, { recursive: true, force: true }); });
  await bridge.activate(context);
  const handshake = () => JSON.parse(fs.readFileSync(bridge.handshakePath, 'utf8'));
  const call = (route = '/health', settings = {}) => {
    const info = handshake();
    return fetch(info.base_url + route, { ...settings, headers: { authorization: `Bearer ${info.token}`, ...settings.headers } });
  };
  return { bridge, context, directory, state, model, vscode, commands, handshake, call };
}

test('health requires the secret and rejects browser origins', async (context) => {
  const fixture = await setup(context);
  assert.equal((await fixture.call()).status, 200);
  assert.equal((await fetch(fixture.handshake().base_url + '/health')).status, 401);
  assert.equal((await fixture.call('/health', { headers: { authorization: 'Bearer wrong' } })).status, 401);
  assert.equal((await fixture.call('/health', { headers: { origin: 'https://example.org' } })).status, 403);
  assert.equal((await fixture.call('/health', { headers: { 'sec-fetch-site': 'same-origin' } })).status, 403);
});

test('visible models do not imply consent', async (context) => {
  const fixture = await setup(context, { permission: false });
  const health = await (await fixture.call()).json();
  assert.equal(health.copilot_available, true);
  assert.equal(health.consented, false);
  const response = await fixture.call('/v1/chat/completions', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ messages: [{ role: 'user', content: 'Hello' }] }) });
  assert.equal(response.status, 403);
  assert.equal(fixture.state.calls, 0);
});

test('finishing the request body does not cancel a model response', async (context) => {
  const fixture = await setup(context);
  const response = await fixture.call('/v1/chat/completions', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ messages: [{ role: 'user', content: 'Hello' }] }) });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).choices[0].message.content, 'ready');
  assert.equal(fixture.state.cancelled, false);
});

test('multiple windows keep independent discovery files', async (context) => {
  const fixture = await setup(context);
  const other = createBridge(fixture.vscode, fixture.directory);
  context.after(() => other.deactivate());
  await other.activate(fixture.context);
  assert.notEqual(other.handshakePath, fixture.bridge.handshakePath);
  await other.deactivate();
  assert.equal(fs.existsSync(fixture.bridge.handshakePath), true);
  assert.equal((await fixture.call()).status, 200);
});

test('a busy preferred port automatically falls back', async (context) => {
  const occupied = http.createServer();
  await new Promise((resolve) => occupied.listen(0, '127.0.0.1', resolve));
  context.after(() => new Promise((resolve) => occupied.close(resolve)));
  const fixture = await setup(context, { port: occupied.address().port });
  assert.notEqual(Number(new URL(fixture.handshake().base_url).port), occupied.address().port);
  assert.equal((await fixture.call()).status, 200);
});

test('concurrent restarts serialize and rotate the session token', async (context) => {
  const fixture = await setup(context);
  const before = fixture.handshake();
  await fixture.call();
  await Promise.all([fixture.commands.get('joblookupBridge.restart')(), fixture.commands.get('joblookupBridge.restart')()]);
  assert.notEqual(fixture.handshake().token, before.token);
  assert.equal((await fixture.call()).status, 200);
});

test('an explicitly unavailable model never silently selects another', async (context) => {
  const fixture = await setup(context);
  const response = await fixture.call('/v1/chat/completions', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ model: 'not-present', messages: [{ role: 'user', content: 'Hello' }] }) });
  assert.equal(response.status, 503);
  assert.equal(fixture.state.calls, 0);
});

test('malformed requests do not crash the server', async (context) => {
  const fixture = await setup(context);
  for (const body of ['{', 'null', '{"messages":"wrong"}', '{"messages":[{"role":"user","content":3}]}']) {
    assert.equal((await fixture.call('/v1/chat/completions', { method: 'POST', headers: { 'content-type': 'application/json' }, body })).status, 400);
  }
  assert.equal((await fixture.call()).status, 200);
});

test('shutdown removes only the instance discovery file', async (context) => {
  const fixture = await setup(context);
  const neighbor = path.join(fixture.directory, 'another-window.json');
  fs.writeFileSync(neighbor, '{}');
  await fixture.bridge.deactivate();
  assert.equal(fs.existsSync(fixture.bridge.handshakePath), false);
  assert.equal(fs.existsSync(neighbor), true);
});