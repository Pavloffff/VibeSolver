import { afterEach, expect, it, vi } from 'vitest'
import observer from '../../public/ui-observer.js?raw'

afterEach(() => { vi.restoreAllMocks(); document.body.replaceChildren() })

it('captures one chosen element locally and lets the engineer cancel the export', async () => {
  document.body.innerHTML = '<h1></h1><ol></ol><a id="capture"></a><p role="status"></p>'
  new Function(observer)()
  const action = document.querySelector<HTMLAnchorElement>('#capture')!.getAttribute('href')!
  document.body.innerHTML = '<label>Access code <input type="password" value="private-value"></label>'
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  new Function(decodeURIComponent(action.slice('javascript:'.length)))()
  const input = document.querySelector('input')!
  input.click()
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(confirm).toHaveBeenCalledTimes(1)
  const prompt = confirm.mock.calls[0]?.[0]
  expect(prompt).toContain('Access code')
  expect(prompt).toContain('"role": "textbox"')
  expect(prompt).not.toContain('private-value')
  input.click()
  expect(confirm).toHaveBeenCalledTimes(1)
})

it.each([false, true])('captures the restored checkbox state when initially %s', async initial => {
  document.body.innerHTML = '<h1></h1><ol></ol><a id="capture"></a><p role="status"></p>'
  new Function(observer)()
  const action = document.querySelector<HTMLAnchorElement>('#capture')!.getAttribute('href')!
  document.body.innerHTML = '<label>Enabled<input type="checkbox"></label>'
  const input = document.querySelector('input')!
  input.checked = initial
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
  new Function(decodeURIComponent(action.slice('javascript:'.length)))()
  input.click()
  await new Promise(resolve => setTimeout(resolve, 0))
  expect(input.checked).toBe(initial)
  expect(confirm.mock.calls[0]?.[0]).toContain(`"checked": ${initial}`)
})

it('uses the language from the helper link when browser preferences differ', () => {
  const url = window.location.href
  window.history.replaceState({}, '', '?lang=zh')
  localStorage.setItem('vibesolver.lang', 'ru')
  document.body.innerHTML = '<h1></h1><ol></ol><a id="capture"></a><p role="status"></p>'
  try {
    new Function(observer)()
    expect(document.documentElement.lang).toBe('zh')
    expect(document.querySelector('h1')?.textContent).toBe('记录界面元素')
  } finally {
    window.history.replaceState({}, '', url)
    localStorage.removeItem('vibesolver.lang')
    document.documentElement.lang = 'en'
  }
})
