import { afterEach, expect, it, vi } from 'vitest'
import { ApiClient } from '../shared/api/client'
import { getLang, initializeDesktopLanguage, saveLang } from '../shared/state/settings'

afterEach(() => vi.unstubAllGlobals())

it('starts the desktop workspace with the language saved in native setup', () => {
  saveLang('en')
  vi.stubGlobal('vibesolver', { initialLanguage: 'zh' })
  initializeDesktopLanguage()
  expect(getLang()).toBe('zh')
  saveLang('ru')
  expect(getLang()).toBe('ru')
})

it.each([
  ['ru', 'Профиль с таким именем уже существует.'],
  ['zh', '同名配置已存在。'],
] as const)('shows a profile conflict in the selected language %s', async (lang, message) => {
  saveLang(lang)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    JSON.stringify({ detail: 'A Solver profile with this name already exists' }), { status: 409 },
  )))
  await expect(new ApiClient(() => '').getSolverGraph(1)).rejects.toThrow(message)
})

it('renders connection failures in the interface language even when the browser is English', async () => {
  saveLang('ru')
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
  await expect(new ApiClient(() => '').checkHealth()).rejects.toThrow('Проверьте адрес сервера и подключение к сети.')
})

it('preserves a diagnostic from an unrecognized provider', async () => {
  saveLang('zh')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(
    JSON.stringify({ detail: 'lab5 gateway: upstream 8 timed out' }), { status: 502 },
  )))
  await expect(new ApiClient(() => '').getSolverGraph(1)).rejects.toThrow('lab5 gateway: upstream 8 timed out')
})

it('explains a required field without displaying the submitted request', async () => {
  saveLang('ru')
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    detail: [{ type: 'missing', loc: ['body', 'name'], msg: 'Field required', input: { token: 'private-input' } }],
  }), { status: 422 })))
  await expect(new ApiClient(() => '').getSolverGraph(1)).rejects.toMatchObject({
    message: 'Ошибка 422: Название — обязательное поле.',
  })
})
