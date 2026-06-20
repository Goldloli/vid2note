const { randomBytes } = require('node:crypto')

function createSessionToken() {
  return randomBytes(32).toString('base64url')
}

function withSessionToken(environment, token) {
  return { ...environment, VID2NOTE_API_TOKEN: token }
}

module.exports = { createSessionToken, withSessionToken }
