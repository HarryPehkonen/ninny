# JSON Pointer, RFC 6901

Implement `src/pointer.js`. Two functions, and a frozen command line on top of them:

```
$ echo '{"a":{"b":[10,20]}}' | node src/cli.js get /a/b/1
20
$ node src/cli.js parse '/a~1b/m~0n'
"a/b"
"m~n"
```

## The two functions

`parsePointer(text)` -> an array of decoded reference tokens, or `null` if `text` is not a
well-formed JSON Pointer.

`resolve(document, text)` -> `{found: true, value}` or `{found: false}`.

## What a pointer is

The empty string, or a sequence of `/` followed by a reference token, repeated. Anything that is
not the empty string and does not begin with `/` is not a JSON Pointer, so `parsePointer` returns
`null` for it. `/` on its own is one reference token, the empty string.

## Decoding a reference token (RFC 6901 section 3)

> Evaluation of each reference token begins by decoding any escaped character
> sequence.  This is performed by first transforming any occurrence of the
> sequence `~1` to `/`, and then transforming any occurrence of the sequence
> `~0` to `~`.  It is an error if the sequence `~` is followed by anything
> other than `0` or `1`.

So the token `a~1b` is the key `a/b`, and `m~0n` is the key `m~n`. A `~` followed by anything other
than `0` or `1` makes the token — and therefore the pointer — not well-formed.

## Resolution (RFC 6901 section 4)

The empty pointer refers to the whole document. Otherwise walk the reference tokens from left to
right, one document level each:

- A token applied to an **object** refers to the member whose name is exactly that token. If there
  is no such member, the pointer does not resolve.
- A token applied to an **array** must be an array index: either the single digit `0`, or a sequence
  of digits that does not begin with `0`. An index that is not less than the array's length does not
  resolve. The single character `-` refers to the element *after* the last one, which is the
  notation JSON Patch uses for "append" — no such element exists in a document being read, so it
  does not resolve either.
- A token applied to a **string, number, boolean or null** does not resolve: those values have no
  members, and a pointer never walks into them.

`resolve` returns `{found: false}` both when the pointer is not well-formed and when it walks off the
document. Call `parsePointer` when you need to tell those two apart.

## The command line (frozen: `src/cli.js`)

```
echo <json> | node src/cli.js get <pointer>   the referenced value as JSON       exit 0
node src/cli.js parse <pointer>               decoded tokens, one per line       exit 0
not well-formed, or no value there            a message on stderr                exit 1
anything else                                 usage on stderr                    exit 2
```

`get` reads the document as JSON from stdin. The file is frozen and shows the exact behaviour;
implement `src/pointer.js`, not the command line.

## The example in the RFC

RFC 6901 section 5 gives this document and these pointers, and both are tested:

```json
{
  "foo": ["bar", "baz"],
  "": 0,
  "a/b": 1,
  "c%d": 2,
  "e^f": 3,
  "g|h": 4,
  "i\\j": 5,
  "k\"l": 6,
  " ": 7,
  "m~n": 8
}
```

| pointer | refers to |
| --- | --- |
| `""` | the whole document |
| `/foo` | `["bar","baz"]` |
| `/foo/0` | `"bar"` |
| `/` | `0`, the member with the empty name |
| `/a~1b` | `1` |
| `/c%d` | `2` |
| `/e^f` | `3` |
| `/g\|h` | `4` |
| `/i\j` | `5` |
| `/k"l` | `6` |
| `/ ` | `7` |
| `/m~0n` | `8` |

## Where the tests go

Every `tests/own/*.test.js` is run by Node's built-in runner, with no packages to install. See
`tests/own/README.md`.
