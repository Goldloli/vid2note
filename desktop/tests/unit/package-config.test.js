const assert = require('node:assert/strict')
const path = require('node:path')
const test = require('node:test')

const packageJson = require('../../package.json')

test('Electron package includes the standalone backend and notices', () => {
  const resources = packageJson.build.extraResources
  const byDestination = new Map(resources.map((resource) => [resource.to, resource.from]))

  assert.equal(byDestination.get('backend'), '../python-dist/vid2note')
  assert.equal(byDestination.get('THIRD_PARTY_NOTICES.md'), '../THIRD_PARTY_NOTICES.md')
  assert.equal(packageJson.scripts['electron:build'].includes('prepare_package.py'), true)
})

test('package smoke exercises the built app instead of a development Electron launch', () => {
  assert.equal(
    packageJson.scripts['test:package'],
    'node tests/package-smoke.js',
  )
  assert.equal(path.basename(packageJson.scripts['test:package']), 'package-smoke.js')
})
