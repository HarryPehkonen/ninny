// FROZEN -- the command line the tool presents. Implement src/duration.js, not this.
//
//   node src/cli.js parse <text>       seconds on stdout          exit 0
//   node src/cli.js format <seconds>   canonical duration         exit 0
//   anything else                      usage on stderr            exit 2
//   input the contract rejects         a message on stderr        exit 1
'use strict';

const { parseDuration, formatDuration } = require('./duration.js');

function usage() {
  process.stderr.write(
    'usage: node src/cli.js parse <text>       seconds from a canonical duration\n' +
    '       node src/cli.js format <seconds>   the canonical duration\n'
  );
  return 2;
}

function main(argv) {
  if (argv.length !== 4) return usage();
  const [, , mode, arg] = argv;

  if (mode === 'parse') {
    const seconds = parseDuration(arg);
    if (seconds === null || seconds === undefined) {
      process.stderr.write(`dur: "${arg}" is not a canonical duration\n`);
      return 1;
    }
    process.stdout.write(`${seconds}\n`);
    return 0;
  }

  if (mode === 'format') {
    if (!/^\d+$/.test(arg)) {
      process.stderr.write(`dur: "${arg}" is not a whole number of seconds\n`);
      return 1;
    }
    const seconds = Number(arg);
    if (!Number.isSafeInteger(seconds)) {
      process.stderr.write(`dur: "${arg}" is too large for a safe integer\n`);
      return 1;
    }
    const text = formatDuration(seconds);
    if (text === null || text === undefined) {
      process.stderr.write(`dur: "${arg}" cannot be formatted\n`);
      return 1;
    }
    process.stdout.write(`${text}\n`);
    return 0;
  }

  return usage();
}

process.exitCode = main(process.argv);
