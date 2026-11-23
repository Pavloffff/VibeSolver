import test from 'node:test'
import assert from 'node:assert/strict'
import http from 'node:http'
import { chromium } from 'playwright-core'
import { observe } from './server.mjs'

const executablePath = process.env.VIBESOLVER_UI_PROBE_TEST_BROWSER

test('real browser reads a configured button and blocks side effects and frames', { skip: !executablePath }, async () => {
  let postCount = 0
  let frameCount = 0
  const server = http.createServer((req, res) => {
    if (req.url === '/post') postCount++
    if (req.url === '/frame') frameCount++
    res.setHeader('content-type', 'text/html')
    res.end('<button>Projects</button><iframe src="/frame"></iframe><script>fetch("/post", {method:"POST"})</script>')
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  try {
    const port = server.address().port
    const result = await observe({ url: `http://127.0.0.1:${port}/`, role: 'button', name: 'Projects' }, executablePath, chromium)
    assert.equal(result.role, 'button')
    assert.equal(result.name, 'Projects')
    assert.equal(result.visible, true)
    assert.equal(result.enabled, true)
    assert.equal(result.checked, null)
    assert.ok(result.width > 0 && result.height > 0)
    assert.equal(postCount, 0)
    assert.equal(frameCount, 0)
  } finally { await new Promise(resolve => server.close(resolve)) }
})
