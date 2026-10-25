// Plausible, and wrong -- THE trap this task exists for.
//
// The RFC says to transform `~1` to `/` first and `~0` to `~` second, and says why. This does it
// in the other order, so `~01` becomes `~1` (correct so far) and then that `~1` becomes `/`.
// RFC 6901: "the string '~01' correctly becomes '~1' after transformation."
//
// Every pointer in the RFC's own section 5 example set still passes: that set contains `~1` and
// `~0`, and nothing whose correct decoding depends on the order.
'use strict';

function decodeToken(token) {
  return token.replace(/~0/g, '~').replace(/~1/g, '/');
}

function parsePointer(text) {
  if (typeof text !== 'string') return null;
  if (text === '') return [];
  if (text[0] !== '/') return null;
  return text.slice(1).split('/').map(decodeToken);
}

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
      if (!Object.prototype.hasOwnProperty.call(value, token)) return { found: false };
      value = value[token];
    } else {
      return { found: false };
    }
  }
  return { found: true, value };
}

module.exports = { parsePointer, resolve };
