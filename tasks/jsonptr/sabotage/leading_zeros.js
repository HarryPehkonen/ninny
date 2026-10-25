// Plausible, and wrong: "digits are an index". RFC 6901 says an array index is `0` or digits with
// NO leading zero, so `/a/01` names no element. `Number('01')` is 1, and this accepts it.
//
// Self-contained on purpose: a sabotage file that requires a sibling is not a drop-in replacement
// for src/pointer.js, and a mutant that crashes proves nothing. The decode here is CORRECT, so the
// only rule this can be caught by is the index rule.
'use strict';

function decodeToken(token) {
  let out = '';
  for (let i = 0; i < token.length; i += 1) {
    const ch = token[i];
    if (ch !== '~') { out += ch; continue; }
    const next = token[i + 1];
    if (next === '0') out += '~';
    else if (next === '1') out += '/';
    else return null;
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

function resolve(document, text) {
  const tokens = parsePointer(text);
  if (tokens === null) return { found: false };
  let value = document;
  for (const token of tokens) {
    if (Array.isArray(value)) {
      if (!/^\d+$/.test(token)) return { found: false };      // the bug: leading zeros accepted
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
