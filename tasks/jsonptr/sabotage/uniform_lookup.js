// Plausible, and wrong: one uniform property lookup, no type check. It works for the happy path
// and leaks everything the language puts on the value: `/a/length` on an array reads the array's
// length, `/s/0` on a string reads its first character, and `/o/toString` finds
// Object.prototype's method. RFC 6901 walks own members of objects and indices of arrays, nothing
// else, and never walks into a string, number, boolean or null.
//
// Self-contained; the decode is CORRECT.
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
    if (value === null || value === undefined) return { found: false };
    if (Array.isArray(value) && !/^(0|[1-9][0-9]*)$/.test(token) && token !== 'length') {
      return { found: false };
    }
    value = value[token];                                     // the bug: no type check at all
    if (value === undefined) return { found: false };
  }
  return { found: true, value };
}

module.exports = { parsePointer, resolve };
