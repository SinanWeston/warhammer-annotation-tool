/**
 * Simple static file server for frontend
 */

import express from 'express'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const app = express()
const PORT = 3003

app.use(express.static(path.join(__dirname, 'frontend/public')))

app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend/public/index.html'))
})

// Clean URL for the labelling tool.
app.get('/label', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend/public/label.html'))
})

app.listen(PORT, () => {
  console.log(`🌐 Frontend running on http://localhost:${PORT}`)
  console.log(`   Analyzer:  http://localhost:${PORT}/`)
  console.log(`   Labeller:  http://localhost:${PORT}/label`)
})
