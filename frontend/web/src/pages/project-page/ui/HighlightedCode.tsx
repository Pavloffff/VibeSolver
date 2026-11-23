import hljs from 'highlight.js/lib/common'

const languageByExtension = new Map(Object.entries({
  bash: 'bash', sh: 'bash', zsh: 'bash',
  c: 'c', h: 'c', cc: 'cpp', cpp: 'cpp', cxx: 'cpp', hpp: 'cpp', cs: 'csharp',
  css: 'css', less: 'less', scss: 'scss',
  diff: 'diff', patch: 'diff', go: 'go', graphql: 'graphql', gql: 'graphql',
  html: 'xml', htm: 'xml', svg: 'xml', xml: 'xml', xsd: 'xml',
  ini: 'ini', cfg: 'ini', toml: 'ini',
  java: 'java', js: 'javascript', jsx: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', tsx: 'typescript', mts: 'typescript', cts: 'typescript',
  json: 'json', jsonl: 'json', yaml: 'yaml', yml: 'yaml',
  kt: 'kotlin', kts: 'kotlin', lua: 'lua', m: 'objectivec', mm: 'objectivec',
  md: 'markdown', markdown: 'markdown', mk: 'makefile',
  php: 'php', pl: 'perl', pm: 'perl', py: 'python', pyi: 'python',
  r: 'r', rb: 'ruby', rs: 'rust', sql: 'sql', swift: 'swift', vb: 'vbnet', wat: 'wasm',
}))

const languageByName = new Map([
  ['gemfile', 'ruby'],
  ['gnumakefile', 'makefile'],
  ['makefile', 'makefile'],
  ['rakefile', 'ruby'],
])

export default function HighlightedCode({ path, content }: { path: string; content: string }) {
  const name = (path.split('/').at(-1) ?? '').toLowerCase()
  const extension = name.slice(name.lastIndexOf('.') + 1)
  const language = languageByName.get(name) ?? (extension !== name ? languageByExtension.get(extension) : undefined)
  if (language === undefined) return <code>{content}</code>

  const tokens = hljs.highlight(content, { language, ignoreIllegals: true }).value
  return <code dangerouslySetInnerHTML={{ __html: tokens }} />
}
