const translations = {
  en: {
    title: 'Capture a UI observation', link: 'Inspect one element',
    steps: ['Drag the link below to your bookmarks bar.', 'In the application you want to inspect, open that bookmark and click the element. Press Escape to cancel.', 'Review the measurements and label in the confirmation. Save the JSON file and attach it to the issue in VibeSolver.'],
    confirm: 'Save this observation as a JSON file?', hint: 'Drag this link to the bookmarks bar, then open it in the target application.',
  },
  ru: {
    title: 'Снять наблюдение об элементе', link: 'Измерить элемент',
    steps: ['Перетащите ссылку ниже на панель закладок браузера.', 'В открытом приложении вызовите эту закладку и нажмите на нужный элемент. Для отмены нажмите Escape.', 'Проверьте размеры и подпись в окне подтверждения. Сохраните JSON-файл и приложите его к обращению в VibeSolver.'],
    confirm: 'Сохранить это наблюдение в JSON-файл?', hint: 'Перетащите ссылку на панель закладок и вызовите её в нужном приложении.',
  },
  zh: {
    title: '记录界面元素', link: '检查一个元素',
    steps: ['将下面的链接拖到浏览器书签栏。', '在要检查的应用中打开此书签，然后点击目标元素。按 Escape 取消。', '在确认框中核对尺寸和标签。保存 JSON 文件并在 VibeSolver 工单中上传。'],
    confirm: '将此记录保存为 JSON 文件吗？', hint: '将链接拖到书签栏，然后在目标应用中打开它。',
  },
}

function inspectElement(confirmText) {
  function stop() {
    document.removeEventListener('click', inspect, true)
    document.removeEventListener('keydown', cancel, true)
  }
  function cancel(event) {
    if (event.key === 'Escape') stop()
  }
  function inspect(event) {
    event.preventDefault()
    event.stopImmediatePropagation()
    stop()
    const target = event.composedPath().find(item => item instanceof Element)
    if (!target) return
    const element = target.closest('label')?.control ?? target.closest('button,input,select,textarea,a,[role]') ?? target
    const roles = { BUTTON: 'button', SELECT: 'combobox', TEXTAREA: 'textbox', A: 'link', IMG: 'img' }
    const inputRoles = { checkbox: 'checkbox', radio: 'radio', button: 'button', submit: 'button', range: 'slider' }
    const role = element.getAttribute('role')?.split(' ')[0] || roles[element.tagName] || (element.tagName === 'INPUT' ? inputRoles[element.type] || 'textbox' : 'generic')
    const label = element.getAttribute('aria-label')
      || (element.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim()
      || element.labels?.[0]?.textContent || (role === 'button' || role === 'link' ? element.textContent : '') || ''
    setTimeout(() => {
      const rect = element.getBoundingClientRect()
      const style = getComputedStyle(element)
      const checkState = element.getAttribute('aria-checked')
      const data = JSON.stringify({
        role, name: label.replace(/\s+/g, ' ').trim().slice(0, 180),
        width: Math.round(rect.width * 100) / 100, height: Math.round(rect.height * 100) / 100,
        visible: rect.width > 0 && rect.height > 0 && !['collapse', 'hidden'].includes(style.visibility),
        enabled: !element.matches(':disabled') && !element.closest('[aria-disabled="true"],[inert]'),
        checked: ['radio', 'checkbox', 'switch'].includes(role) ? (checkState ? (checkState === 'mixed' ? null : checkState === 'true') : (element.indeterminate ? null : element.checked ?? null)) : null,
        observed_at: new Date().toISOString(),
      }, null, 2)
      if (!window.confirm(confirmText + '\n\n' + data)) return
      const url = URL.createObjectURL(new Blob([data], { type: 'application/json' }))
      const download = document.createElement('a')
      download.href = url
      download.download = 'ui-observation.json'
      download.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    }, 0)
  }
  document.addEventListener('click', inspect, true)
  document.addEventListener('keydown', cancel, true)
}

const requestedLang = location.protocol === 'file:'
  ? document.documentElement.lang
  : new URLSearchParams(location.search).get('lang') ?? localStorage.getItem('vibesolver.lang')
const lang = requestedLang === 'ru' || requestedLang === 'zh' ? requestedLang : 'en'
const copy = translations[lang]
document.documentElement.lang = lang
document.title = copy.title + ' · VibeSolver'
document.querySelector('h1').textContent = copy.title
for (const instruction of copy.steps) {
  const item = document.createElement('li')
  item.textContent = instruction
  document.querySelector('ol').append(item)
}
const capture = document.querySelector('#capture')
capture.textContent = copy.link
capture.href = 'javascript:' + encodeURIComponent('(' + inspectElement.toString() + ')(' + JSON.stringify(copy.confirm) + ');void 0')
capture.addEventListener('click', event => {
  event.preventDefault()
  document.querySelector('[role="status"]').textContent = copy.hint
})
