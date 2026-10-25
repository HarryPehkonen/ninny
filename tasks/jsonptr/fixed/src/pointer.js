// The reference implementation -- the answer key, not a hint. One bug per sabotage file so a
// failure can be attributed to a rule instead of to "somewhere in the decode".
'use strict';

// RFC 6901 section 3: transform `~1` to `/` FIRST, then `~0` to `~`. The order is the entire
// point -- with the other order `~01` becomes `~1` and then `/`, which the RFC calls out as
// incorrect: `~01` denotes the two characters `~1`. A single left-to-right pass, which is what
// this is, gets that right by construction.
function decodeToken(token) {
  let out = '';
  for (let i = 0; i < token.length; i += 1) {
    const ch = token[i];
    if (ch !== '~') {
      out += ch;
      continue;
    }
    const next = token[i + 1];
    if (next === '0') out += '~';
    else if (next === '1') out += '/';
    else return null;            // `~` followed by anything else, including nothing, is an error
    i += 1;
  }
  return out;
}

function parsePointer(text) {
  if (typeof text !== 'string') return null;
  if (text === '') return [];
  if (text[0] !== '/') return null;
  const tokens = [];
  for (const raw of text.slice(1).split('/')) {
    const token = decodeToken(raw);
    if (token === null) return null;
    tokens.push(token);
  }
  return tokens;
}

// An array index is `0` or digits with no leading zero -- so `01` names no element, and neither
// does `-`, which is JSON Patch's "append" and refers to nothing in a document being read.
const INDEX = /^(0|[1-9][0-9]*)$/;

function resolve(document, text) {
  const tokens = parsePointer(text);
  if (tokens === null) return { found: false };
  let value = document;
  for (const token of tokens) {
    if (Array.isArray(value)) {
      if (!INDEX.test(token)) return { found: false };
      const index = Number(token);
      if (index >= value.length) return { found: false };
      value = value[index];
    } else if (value !== null && typeof value === 'object') {
      // Own members only: `/toString` on `{}` names nothing, and a pointer never walks into a
      // string, a number, a boolean or null.
      if (!Object.prototype.hasOwnProperty.call(value, token)) return { found: false };
      value = value[token];
    } else {
      return { found: false };
    }
  }
  return { found: true, value };
}

module.exports = { parsePointer, resolve };
