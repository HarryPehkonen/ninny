// Plausible, and wrong: `-` read as "the last element". RFC 6901 defines `-` as the element AFTER
// the last one -- JSON Patch's "append" -- so it refers to nothing in a document being read.
//
// Self-contained, and the decode and index rules here are CORRECT, so only the `-` rule can fail it.
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
      if (token === '-') {
        value = value[value.length - 1];                      // the bug: `-` as the last element
        if (value === undefined) return { found: false };
        continue;
      }
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
