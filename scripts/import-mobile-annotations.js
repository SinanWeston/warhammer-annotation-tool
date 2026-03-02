#!/usr/bin/env node
/**
 * Import mobile annotations from an exported JSON file into the backend.
 *
 * Usage:
 *   npm run sync:mobile                          # auto-finds newest annotations-*.json in pCloudDrive
 *   npm run sync:mobile -- /path/to/file.json   # explicit file
 */

const fs = require('fs')
const path = require('path')
const http = require('http')
const os = require('os')

function findLatestExport() {
  const pcloudDir = path.join(os.homedir(), 'pCloudDrive')
  try {
    const files = fs.readdirSync(pcloudDir)
      .filter(f => /^annotations-.*\.json$/.test(f))
      .map(f => ({ name: f, mtime: fs.statSync(path.join(pcloudDir, f)).mtimeMs }))
      .sort((a, b) => b.mtime - a.mtime)
    return files.length > 0 ? path.join(pcloudDir, files[0].name) : null
  } catch {
    return null
  }
}

async function main() {
  const filePath = process.argv[2] || findLatestExport()

  if (!filePath) {
    console.error('❌ No file specified and no annotations-*.json found in ~/pCloudDrive')
    console.error('   Usage: npm run sync:mobile -- /path/to/annotations.json')
    process.exit(1)
  }

  if (!fs.existsSync(filePath)) {
    console.error(`❌ File not found: ${filePath}`)
    process.exit(1)
  }

  console.log(`📂 Importing from: ${filePath}`)
  let data = JSON.parse(fs.readFileSync(filePath, 'utf8'))

  // Accept both {annotations:[...]} and raw array
  if (Array.isArray(data)) data = { annotations: data }
  if (!Array.isArray(data.annotations)) {
    console.error('❌ Invalid file format — expected { annotations: [...] }')
    process.exit(1)
  }

  console.log(`📱 ${data.annotations.length} annotation(s) to import`)

  return new Promise((resolve, reject) => {
    const body = JSON.stringify(data)
    const options = {
      hostname: 'localhost',
      port: 3001,
      path: '/api/mobile/sync',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    }

    const req = http.request(options, (res) => {
      let raw = ''
      res.on('data', chunk => raw += chunk)
      res.on('end', () => {
        try {
          const result = JSON.parse(raw)
          const d = result.data || result
          console.log(`✅ Synced: ${d.synced ?? 0}  Skipped (already exist): ${d.skipped ?? 0}`)
          if (d.errors?.length > 0) console.warn('⚠️  Errors:', d.errors)
          console.log('\nDone! Now tap "IMPORTED ON PC — MARK AS SYNCED" in the phone app.')
        } catch {
          console.log('Response:', raw)
        }
        resolve(undefined)
      })
    })

    req.on('error', (e) => {
      console.error('❌ Could not reach backend:', e.message)
      console.error('   Make sure the backend is running: npm run dev:backend')
      reject(e)
    })

    req.write(body)
    req.end()
  })
}

main().catch(() => process.exit(1))
