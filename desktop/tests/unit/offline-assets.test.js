const assert = require('node:assert/strict')
const { readFileSync, readdirSync } = require('node:fs')
const { join } = require('node:path')
const test = require('node:test')

function sourceFiles(root) {
  return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
    const path = join(root, entry.name)
    return entry.isDirectory() ? sourceFiles(path) : [path]
  })
}

test('renderer styles do not load remote assets', () => {
  const styles = join(process.cwd(), 'src', 'renderer', 'styles')
  const remoteReferences = sourceFiles(styles)
    .filter((path) => path.endsWith('.css'))
    .filter((path) => /(?:https?:)?\/\//.test(readFileSync(path, 'utf8')))

  assert.deepEqual(remoteReferences, [])
})
