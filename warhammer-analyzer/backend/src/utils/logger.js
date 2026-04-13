/**
 * Logger Utility
 *
 * Simple console logging with timestamps and levels
 */

const LOG_LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3
}

const CURRENT_LEVEL = LOG_LEVELS[process.env.LOG_LEVEL?.toUpperCase()] ?? LOG_LEVELS.INFO

function formatTimestamp() {
  return new Date().toISOString()
}

function shouldLog(level) {
  return LOG_LEVELS[level] >= CURRENT_LEVEL
}

function log(level, message, ...args) {
  if (!shouldLog(level)) return

  const timestamp = formatTimestamp()
  const prefix = `[${timestamp}] [${level}]`

  switch (level) {
    case 'ERROR':
      console.error(prefix, message, ...args)
      break
    case 'WARN':
      console.warn(prefix, message, ...args)
      break
    case 'DEBUG':
    case 'INFO':
    default:
      console.log(prefix, message, ...args)
  }
}

export const logger = {
  debug: (message, ...args) => log('DEBUG', message, ...args),
  info: (message, ...args) => log('INFO', message, ...args),
  warn: (message, ...args) => log('WARN', message, ...args),
  error: (message, ...args) => log('ERROR', message, ...args)
}
