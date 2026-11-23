import http from 'node:http'
import { pathToFileURL } from 'node:url'

function positiveInt(value, fallback, max) {
  const parsed = value === undefined ? fallback : Number(value)
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > max) throw new Error('Invalid probe limit')
  return parsed
}

export function parseConfig(env) {
  if (!env.VIBESOLVER_UI_PROBE_DEFINITIONS) throw new Error('VIBESOLVER_UI_PROBE_DEFINITIONS is required')
  const definitions = JSON.parse(env.VIBESOLVER_UI_PROBE_DEFINITIONS)
  if (!definitions || typeof definitions !== 'object' || Array.isArray(definitions)) throw new Error('Invalid definitions')
  for (const [alias, target] of Object.entries(definitions)) {
    if (!/^[a-zA-Z0-9_-]+$/.test(alias) || !target || typeof target !== 'object' || typeof target.url !== 'string' || typeof target.role !== 'string' || !target.role || typeof target.name !== 'string' || !target.name) throw new Error('Invalid definition')
    let url
    try { url = new URL(target.url) } catch { throw new Error('Invalid target URL') }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('Invalid target URL')
  }
  if (!env.VIBESOLVER_UI_PROBE_BIND || !env.VIBESOLVER_UI_PROBE_BROWSER || !env.VIBESOLVER_UI_PROBE_PORT) throw new Error('Probe bind, port and browser are required')
  return { bind: env.VIBESOLVER_UI_PROBE_BIND, port: positiveInt(env.VIBESOLVER_UI_PROBE_PORT, 0, 65535), browser: env.VIBESOLVER_UI_PROBE_BROWSER, definitions, timeout: positiveInt(env.VIBESOLVER_UI_PROBE_TIMEOUT_MS, 10000, 60000), concurrency: positiveInt(env.VIBESOLVER_UI_PROBE_CONCURRENCY, 1, 4) }
}

export function isAllowedRequest(request, origin, mainFrame) {
  let url
  try { url = new URL(request.url()) } catch { return false }
  if (url.origin !== origin || !['http:', 'https:'].includes(url.protocol) || !['GET', 'HEAD'].includes(request.method()) || request.resourceType() === 'websocket') return false
  try { return request.frame() === mainFrame } catch { return false }
}

export async function observe(target, executablePath, chromium, timeout = 10000) {
  const browser = await chromium.launch({ executablePath, headless: true, timeout })
  const deadline = setTimeout(() => { void browser.close() }, timeout)
  deadline.unref()
  try {
    const context = await browser.newContext({ serviceWorkers: 'block', acceptDownloads: false })
    try {
      const page = await context.newPage()
      page.setDefaultTimeout?.(timeout)
      page.setDefaultNavigationTimeout?.(timeout)
      await context.routeWebSocket?.('**/*', socket => socket.close())
      await context.route('**/*', route => isAllowedRequest(route.request(), new URL(target.url).origin, page.mainFrame()) ? route.continue() : route.abort())
      page.on?.('popup', popup => { void popup.close() })
      page.on?.('download', download => { void download.cancel() })
      await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout })
      const locator = page.getByRole(target.role, { name: target.name, exact: true, includeHidden: true })
      if (await locator.count() !== 1) throw new Error('Element must have a unique match')
      const visible = await locator.isVisible()
      const box = visible ? await locator.boundingBox() : null
      const checked = ['checkbox', 'radio', 'switch', 'menuitemcheckbox', 'menuitemradio'].includes(target.role) ? await locator.isChecked() : null
      return { role: target.role, name: target.name, width: box?.width ?? 0, height: box?.height ?? 0, visible, enabled: await locator.isEnabled(), checked, observed_at: new Date().toISOString() }
    } finally { await context.close() }
  } finally { clearTimeout(deadline); await browser.close() }
}

export function createProbeServer(config, chromium) {
  let running = 0
  return http.createServer(async (req, res) => {
    const send = (status, body) => { res.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store' }); res.end(JSON.stringify(body)) }
    const url = new URL(req.url ?? '/', 'http://localhost')
    if (req.method !== 'GET' || url.pathname !== '/observe' || [...url.searchParams.keys()].length !== 1 || !url.searchParams.has('probe')) return send(404, { error: 'Not found' })
    const alias = url.searchParams.get('probe')
    if (!alias || !Object.hasOwn(config.definitions, alias)) return send(404, { error: 'Unknown probe' })
    if (running >= config.concurrency) return send(429, { error: 'Probe busy' })
    running++
    try { send(200, await observe(config.definitions[alias], config.browser, chromium, config.timeout)) }
    catch { send(502, { error: 'Observation unavailable' }) }
    finally { running-- }
  })
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const config = parseConfig(process.env)
  const { chromium } = await import('playwright-core')
  createProbeServer(config, chromium).listen(config.port, config.bind)
}
