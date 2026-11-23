import test from 'node:test'
import assert from 'node:assert/strict'
import { parseConfig, isAllowedRequest, observe } from './server.mjs'

test('configuration requires explicit targets and rejects non-http URLs', () => {
  assert.throws(() => parseConfig({}), /DEFINITIONS/)
  assert.throws(() => parseConfig({ VIBESOLVER_UI_PROBE_DEFINITIONS: '{"stand":{"url":"file:///tmp/x","role":"button","name":"Save"}}' }), /url/i)
})

test('requests stay on the configured origin, main frame, GET or HEAD and exclude websockets', () => {
  const origin = 'https://stand.example'
  const req = (url, method = 'GET', frame = true, type = 'document') => ({ url: () => url, method: () => method, isNavigationRequest: () => true, frame: () => frame ? 1 : 2, resourceType: () => type })
  assert.equal(isAllowedRequest(req('https://stand.example/a'), origin, 1), true)
  assert.equal(isAllowedRequest(req('https://evil.example/'), origin, 1), false)
  assert.equal(isAllowedRequest(req('https://stand.example/', 'POST'), origin, 1), false)
  assert.equal(isAllowedRequest(req('https://stand.example/', 'GET', false), origin, 1), false)
  assert.equal(isAllowedRequest(req('wss://stand.example/', 'GET', true, 'websocket'), origin, 1), false)
})

test('observe rejects nonunique matches and closes the isolated browser', async () => {
  let closed = false
  const page = { route: async () => {}, goto: async () => {}, mainFrame: () => 1, getByRole: () => ({ count: async () => 2 }) }
  const browser = { newContext: async () => ({ newPage: async () => page, route: async () => {}, close: async () => {} }), close: async () => { closed = true } }
  await assert.rejects(observe({ url: 'http://localhost:9000/', role: 'button', name: 'Save' }, 'browser', { launch: async () => browser }), /unique/i)
  assert.equal(closed, true)
})

test('HTTP accepts configured aliases only and bounds concurrent launches', async () => {
  let release
  const gate = new Promise(resolve => { release = resolve })
  const page = { mainFrame: () => 1, goto: async () => gate, getByRole: () => ({ count: async () => 0 }) }
  const chromium = { launch: async () => ({ newContext: async () => ({ newPage: async () => page, route: async () => {}, close: async () => {} }), close: async () => {} }) }
  const { createProbeServer } = await import('./server.mjs')
  const config = { definitions: { example: { url: 'http://localhost:9999/', role: 'button', name: 'Open' } }, browser: 'browser', concurrency: 1, timeout: 1000 }
  const server = createProbeServer(config, chromium)
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  try {
    const base = `http://127.0.0.1:${server.address().port}`
    assert.equal((await fetch(`${base}/observe?probe=unknown`)).status, 404)
    assert.equal((await fetch(`${base}/observe?probe=example&url=http://evil/`)).status, 404)
    assert.equal((await fetch(`${base}/observe?probe=example`, { method: 'POST' })).status, 404)
    const first = fetch(`${base}/observe?probe=example`)
    await new Promise(resolve => setImmediate(resolve))
    assert.equal((await fetch(`${base}/observe?probe=example`)).status, 429)
    release()
    assert.equal((await first).status, 502)
  } finally { release(); await new Promise(resolve => server.close(resolve)) }
})
