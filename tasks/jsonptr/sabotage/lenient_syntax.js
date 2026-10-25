// Plausible, and wrong: a lenient parser. A JSON Pointer is the empty string or begins with `/`,
// and anything else is not a pointer at all -- this accepts `foo` as the single token `foo`, and
// `/a~2b` as the token `a~2b`.
//
// Self-contained; the resolution here is CORRECT, and so is the decoding of well-formed escapes.
'use strict';

function decodeToken(token) {
  let out = '';
  for (let i = 0; i < token.length; i += 1) {
    const ch = token[i];
    if (ch !== '~') { out += ch; continue; }
    const next = token[i + 1];
    if (next === '0') out += '~';
    else if (next === '1') out += '/';
    else { out += ch; continue; }                             // the bug: a bad escape passes through
    i += 1;
  }
  return out;
}

function parsePointer(text) {
  if (typeof text !== 'string') return null;
  if (text === '') return [];
  const body = text[0] === '/' ? text.slice(1) : text;        // the bug: no leading slash required
  return body.split('/').map(decodeToken);
}

function resolve(document, text) {
  const tokens = parsePointer(text);
  if (tokens === null) return { found: false };
  let value = document;
  for (const token of tokens) {
    if (Array.isArray(value)) {
      if (!/^(0|[1-9][0-9]*)$/.test(token)) return { found: false };
      const index = Number(token);
      if (index >= value.length) return { found: false };
      value = value[index];
    } else if (value !== null && typeof value === 'object') {
      if (!Object.prototype.hasOwnProperty.call(value, token)) return { found: false };
      value = value[token];
    } else {
      return { found: false };
    }
  }
  return { found: true, value };
}

module.exports = { parsePointer, resolve };
