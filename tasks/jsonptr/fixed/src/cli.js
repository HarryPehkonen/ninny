// FROZEN -- the command line the tool presents. Implement src/pointer.js, not this.
//
//   echo <json> | node src/cli.js get <pointer>   the referenced value as JSON   exit 0
//   node src/cli.js parse <pointer>               decoded tokens, one per line   exit 0
//   not well-formed, or no value there            a message on stderr            exit 1
//   anything else                                 usage on stderr                exit 2
'use strict';

const fs = require('fs');
const { parsePointer, resolve } = require('./pointer.js');

function usage() {
  process.stderr.write(
    'usage: echo <json> | node src/cli.js get <pointer>\n' +
    '       node src/cli.js parse <pointer>\n'
  );
  return 2;
}

function stdin() {
  try {
    return fs.readFileSync(0, 'utf8');
  } catch (err) {
    return '';
  }
}

function main(argv) {
  if (argv.length !== 4) return usage();
  const [, , mode, arg] = argv;

  if (mode === 'parse') {
    const tokens = parsePointer(arg);
    if (tokens === null || tokens === undefined) {
      process.stderr.write(`jsonptr: "${arg}" is not a well-formed JSON Pointer\n`);
      return 1;
    }
    for (const token of tokens) process.stdout.write(`${JSON.stringify(token)}\n`);
    return 0;
  }

  if (mode === 'get') {
    if (parsePointer(arg) === null || parsePointer(arg) === undefined) {
      process.stderr.write(`jsonptr: "${arg}" is not a well-formed JSON Pointer\n`);
      return 1;
    }
    let document;
    try {
      document = JSON.parse(stdin());
    } catch (err) {
      process.stderr.write('jsonptr: stdin is not JSON\n');
      return 1;
    }
    const result = resolve(document, arg);
    if (!result || !result.found) {
      process.stderr.write(`jsonptr: no value at "${arg}"\n`);
      return 1;
    }
    process.stdout.write(`${JSON.stringify(result.value)}\n`);
    return 0;
  }

  return usage();
}

process.exitCode = main(process.argv);
