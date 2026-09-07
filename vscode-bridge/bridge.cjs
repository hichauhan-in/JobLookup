const http = require('node:http');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');

const MAX_BODY = 2 * 1024 * 1024;
const MAX_OUTPUT = 2 * 1024 * 1024;
const PREFERRED = ['gpt-4o-mini', 'gpt-5-mini', 'gpt-5.4-mini', 'claude-haiku-4.5', 'gpt-4o'];

function createBridge(vscode, directory = path.join(os.homedir(), '.joblookup', 'bridges')) {
  const instance = `${process.pid}-${crypto.randomBytes(8).toString('hex')}`;
  const handshake = path.join(directory, `${instance}.json`);
  let server = null;
  let token = '';
  let heartbeat = null;
  let context = null;
  let output = null;
  let statusBar = null;
  let consented = false;
  let pending = 0;
  let lifecycle = Promise.resolve();
  const cancellations = new Set();

  const config = () => vscode.workspace.getConfiguration('joblookupBridge');
  const log = (message) => output?.appendLine(message);
  const serialize = (operation) => {
    const result = lifecycle.then(operation);
    lifecycle = result.catch((error) => log(error.message));
    return result;
  };

  function publish() {
    const address = server?.address();
    if (!address) return;
    fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
    const temporary = `${handshake}.tmp`;
    fs.writeFileSync(temporary, JSON.stringify({
      base_url: `http://127.0.0.1:${address.port}`, token, pid: process.pid,
      instance, version: '0.4.0', updated_at: new Date().toISOString(),
    }), { mode: 0o600 });
    fs.renameSync(temporary, handshake);
  }

  function paint() {
    if (!statusBar) return;
    const address = server?.address();
    statusBar.text = address ? '$(broadcast) JobLookup' : '$(circle-slash) JobLookup';
    statusBar.tooltip = address ? `Bridge listening on 127.0.0.1:${address.port}` : 'Bridge stopped';
    statusBar.show();
  }

  async function models() {
    try { return await vscode.lm.selectChatModels({ vendor: 'copilot' }); }
    catch (error) { log(`Model discovery failed: ${error.message}`); return []; }
  }

  function choose(available, requested) {
    const wanted = requested || config().get('modelFamily') || '';
    if (wanted) return available.find((model) => [model.id, model.family, model.name].includes(wanted));
    return PREFERRED.map((family) => available.find((model) => model.family === family)).find(Boolean) || available[0];
  }

  function allowed(model) {
    const permission = context?.languageModelAccessInformation?.canSendRequest(model);
    return permission === true || (permission === undefined && consented);
  }

  function send(response, status, payload) {
    if (response.destroyed || response.writableEnded) return;
    const body = JSON.stringify(payload);
    response.writeHead(status, {
      'content-type': 'application/json; charset=utf-8',
      'content-length': Buffer.byteLength(body), 'cache-control': 'no-store',
    });
    response.end(body);
  }

  function authenticated(request) {
    const header = String(request.headers.authorization || '');
    const provided = Buffer.from(header.startsWith('Bearer ') ? header.slice(7) : '');
    const expected = Buffer.from(token);
    return provided.length === expected.length && provided.length > 0 && crypto.timingSafeEqual(provided, expected);
  }

  async function bodyOf(request) {
    if (!String(request.headers['content-type'] || '').startsWith('application/json')) {
      throw Object.assign(new Error('Expected application/json.'), { status: 415 });
    }
    const chunks = [];
    let size = 0;
    for await (const chunk of request) {
      size += chunk.length;
      if (size > MAX_BODY) throw Object.assign(new Error('Request body is too large.'), { status: 413 });
      chunks.push(chunk);
    }
    try {
      const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (!body || typeof body !== 'object' || Array.isArray(body)) throw new Error();
      return body;
    } catch { throw Object.assign(new Error('Expected a JSON object.'), { status: 400 }); }
  }

  async function health(response) {
    const available = await models();
    const selected = choose(available);
    send(response, 200, {
      ok: true, instance, version: '0.4.0',
      copilot_available: available.length > 0,
      consented: Boolean(selected && allowed(selected)),
      models: available.map((model) => model.family || model.id),
      default_model: selected?.family || selected?.id || '',
    });
  }

  async function chat(request, response) {
    if (pending >= 2) { send(response, 429, { error: 'The bridge is busy. Wait for the current requests to finish.' }); return; }
    pending += 1;
    const cancellation = new vscode.CancellationTokenSource();
    cancellations.add(cancellation);
    const abort = () => { if (!response.writableEnded) cancellation.cancel(); };
    response.once('close', abort);
    let timer;
    try {
      const payload = await bodyOf(request);
      if (!Array.isArray(payload.messages) || payload.messages.length === 0 || payload.messages.length > 100) {
        throw Object.assign(new Error('Supply between 1 and 100 chat messages.'), { status: 400 });
      }
      if (payload.messages.some((message) => !message || typeof message.content !== 'string' || !['system', 'user', 'assistant'].includes(message.role))) {
        throw Object.assign(new Error('Invalid chat message.'), { status: 400 });
      }
      const available = await models();
      const model = choose(available, payload.model);
      if (!model) throw Object.assign(new Error(payload.model ? 'The requested model is not available.' : 'No Copilot models are available in this window.'), { status: 503 });
      if (!allowed(model)) throw Object.assign(new Error("Run 'JobLookup Bridge: Authorise Copilot Access' in VS Code first."), { status: 403 });
      const messages = payload.messages.map((message) => message.role === 'assistant'
        ? vscode.LanguageModelChatMessage.Assistant(message.content)
        : vscode.LanguageModelChatMessage.User(message.content));
      const generate = async () => {
        if (model.countTokens && model.maxInputTokens) {
          let count = 0;
          for (const message of payload.messages) count += await model.countTokens(message.content);
          if (count > model.maxInputTokens) throw Object.assign(new Error('The document exceeds this model\'s context limit.'), { status: 413 });
        }
        const answer = await model.sendRequest(messages, {}, cancellation.token);
        let content = '';
        for await (const fragment of answer.text) {
          content += fragment;
          if (content.length > MAX_OUTPUT) throw new Error('The model response exceeded the size limit.');
        }
        if (!content.trim()) throw new Error('The model returned an empty response.');
        consented = true;
        return content;
      };
      const deadline = new Promise((_, reject) => {
        timer = setTimeout(() => { cancellation.cancel(); reject(Object.assign(new Error('The model request timed out.'), { status: 504 })); }, 180_000);
        timer.unref?.();
      });
      const content = await Promise.race([generate(), deadline]);
      send(response, 200, { model: model.id, choices: [{ message: { role: 'assistant', content }, finish_reason: 'stop', index: 0 }] });
    } catch (error) {
      const status = error.status || (error.code === 'NoPermissions' ? 403 : 502);
      send(response, status, { error: error.message || 'The model request failed.' });
    } finally {
      clearTimeout(timer);
      response.off('close', abort);
      cancellations.delete(cancellation);
      cancellation.dispose();
      pending -= 1;
    }
  }

  function listen(port) {
    return new Promise((resolve, reject) => {
      const candidate = http.createServer((request, response) => {
        const dispatch = async () => {
          if (request.headers.origin || request.headers['sec-fetch-site']) { send(response, 403, { error: 'Browser requests are not accepted.' }); return; }
          if (!authenticated(request)) { send(response, 401, { error: 'Missing or invalid bearer token.' }); return; }
          const route = (request.url || '').split('?')[0];
          if (request.method === 'GET' && route === '/health') await health(response);
          else if (request.method === 'POST' && route === '/v1/chat/completions') await chat(request, response);
          else send(response, 404, { error: 'Unknown bridge route.' });
        };
        void dispatch().catch((error) => send(response, 500, { error: error.message }));
      });
      candidate.requestTimeout = 30_000;
      candidate.headersTimeout = 15_000;
      candidate.once('error', reject);
      candidate.listen(port, '127.0.0.1', () => {
        candidate.off('error', reject);
        candidate.on('error', (error) => log(`Bridge server: ${error.message}`));
        server = candidate;
        resolve(candidate.address().port);
      });
    });
  }

  async function stop() {
    clearInterval(heartbeat);
    heartbeat = null;
    for (const cancellation of cancellations) cancellation.cancel();
    const previous = server;
    server = null;
    if (previous) await new Promise((resolve) => { previous.close(resolve); previous.closeAllConnections?.(); });
    fs.rmSync(handshake, { force: true });
    fs.rmSync(`${handshake}.tmp`, { force: true });
    paint();
  }

  async function start() {
    if (server?.listening) return server.address().port;
    token = crypto.randomBytes(32).toString('hex');
    const preferred = Number(config().get('port') ?? 8771);
    if (!Number.isInteger(preferred) || preferred < 0 || preferred > 65535) throw new Error('Bridge port must be between 0 and 65535.');
    let port;
    try { port = await listen(preferred); }
    catch (error) {
      if (error.code !== 'EADDRINUSE') throw error;
      port = await listen(0);
      log(`Preferred port is occupied; using ${port}.`);
    }
    try { publish(); }
    catch (error) { await stop(); throw error; }
    heartbeat = setInterval(() => {
      try { publish(); } catch (error) { log(`Discovery file could not be updated: ${error.message}`); }
    }, 15_000);
    heartbeat.unref?.();
    paint();
    log(`Bridge ready at 127.0.0.1:${port}.`);
    return port;
  }

  async function activate(extensionContext) {
    context = extensionContext;
    output = vscode.window.createOutputChannel('JobLookup Bridge');
    statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBar.command = 'joblookupBridge.status';
    const showError = async (error) => {
      const selection = await vscode.window.showErrorMessage(`JobLookup Bridge: ${error.message}`, 'Show log');
      if (selection === 'Show log') output.show();
    };
    context.subscriptions.push(output, statusBar,
      vscode.commands.registerCommand('joblookupBridge.restart', async () => {
        try { const port = await serialize(async () => { await stop(); return start(); }); await vscode.window.showInformationMessage(`JobLookup Bridge is listening on ${port}.`); }
        catch (error) { await showError(error); }
      }),
      vscode.commands.registerCommand('joblookupBridge.status', async () => {
        const available = await models();
        await vscode.window.showInformationMessage(server?.listening ? `Bridge ready on ${server.address().port}; ${available.length} Copilot models available.` : 'Bridge is stopped.');
      }),
      vscode.commands.registerCommand('joblookupBridge.authorize', async () => {
        const cancellation = new vscode.CancellationTokenSource();
        try {
          const model = choose(await models());
          if (!model) throw new Error('Sign in to GitHub Copilot before authorizing the bridge.');
          const response = await model.sendRequest([vscode.LanguageModelChatMessage.User('Reply with the word ready.')], {}, cancellation.token);
          for await (const fragment of response.text) { if (fragment) { consented = true; break; } }
          if (!consented) throw new Error('The authorization test returned no response.');
          await vscode.window.showInformationMessage(`JobLookup can use ${model.name}.`);
        } catch (error) { await showError(error); }
        finally { cancellation.cancel(); cancellation.dispose(); }
      }),
    );
    if (config().get('autoStart') !== false) {
      try { await serialize(start); } catch (error) { await showError(error); }
    }
    paint();
  }

  return { activate, deactivate: () => serialize(stop), handshakePath: handshake };
}

let extension;
exports.createBridge = createBridge;
exports.activate = async (context) => {
  extension = createBridge(require('vscode'));
  await extension.activate(context);
};
exports.deactivate = () => extension?.deactivate();