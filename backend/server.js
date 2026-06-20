const http = require('http');
const fs = require('fs');
const path = require('path');
const dbHelper = require('./database');
const UrbanSimulator = require('./simulator');

const PORT = process.env.PORT || 3000;

// SSE Client list
let clients = [];

// Helper to broadcast real-time events to all SSE clients
function broadcast(type, data) {
  const payload = JSON.stringify({ type, data });
  clients.forEach(client => {
    client.write(`data: ${payload}\n\n`);
  });
}

// Instantiate simulator with SSE broadcast callback
const simulator = new UrbanSimulator((type, data) => {
  broadcast(type, data);
});

// Periodic statistics broadcast (every 1 second)
setInterval(() => {
  if (clients.length > 0) {
    broadcast('stats', simulator.getStats());
  }
}, 1000);

// Helper to serve static assets from frontend
function serveStaticFile(reqUrl, res) {
  let relativePath = reqUrl === '/' || reqUrl === '' ? 'index.html' : reqUrl;
  
  // Resolve path safely to avoid traversal
  const resolvedPath = path.resolve(path.join(__dirname, '..', 'frontend', relativePath));
  const frontendDir = path.resolve(path.join(__dirname, '..', 'frontend'));

  if (!resolvedPath.startsWith(frontendDir)) {
    res.writeHead(403, { 'Content-Type': 'text/plain' });
    res.end('403 Forbidden');
    return;
  }

  if (fs.existsSync(resolvedPath) && fs.statSync(resolvedPath).isFile()) {
    const ext = path.extname(resolvedPath).toLowerCase();
    let contentType = 'text/plain';
    
    if (ext === '.html') contentType = 'text/html';
    else if (ext === '.css') contentType = 'text/css';
    else if (ext === '.js') contentType = 'application/javascript';
    else if (ext === '.png') contentType = 'image/png';
    else if (ext === '.jpg' || ext === '.jpeg') contentType = 'image/jpeg';
    else if (ext === '.svg') contentType = 'image/svg+xml';
    else if (ext === '.ico') contentType = 'image/x-icon';

    res.writeHead(200, {
      'Content-Type': contentType,
      'Access-Control-Allow-Origin': '*'
    });
    fs.createReadStream(resolvedPath).pipe(res);
  } else {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('404 Not Found');
  }
}

// Unified Request Handler
const server = http.createServer((req, res) => {
  const parsedUrl = new URL(req.url, `http://${req.headers.host}`);
  const pathname = parsedUrl.pathname;
  const method = req.method;

  // Add CORS headers for simplicity
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // 1. SERVER-SENT EVENTS (SSE) STREAM
  if (pathname === '/api/events' && method === 'GET') {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*'
    });

    // Send initial states
    res.write(`data: ${JSON.stringify({ type: 'stats', data: simulator.getStats() })}\n\n`);
    
    clients.push(res);

    req.on('close', () => {
      clients = clients.filter(c => c !== res);
    });
    return;
  }

  // 2. API ENDPOINTS
  
  // GET /api/user/:username
  const userMatch = pathname.match(/^\/api\/user\/([^/]+)$/);
  if (userMatch && method === 'GET') {
    const username = decodeURIComponent(userMatch[1]);
    const user = dbHelper.getUser(username);
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(user));
    return;
  }

  // GET /api/leaderboard
  if (pathname === '/api/leaderboard' && method === 'GET') {
    const leaderboard = dbHelper.getAllUsers();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(leaderboard));
    return;
  }

  // GET /api/ledger
  if (pathname === '/api/ledger' && method === 'GET') {
    const ledger = dbHelper.getLedger();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(ledger.slice(0, 100)));
    return;
  }

  // GET /api/dashboard/stats
  if (pathname === '/api/dashboard/stats' && method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(simulator.getStats()));
    return;
  }

  // POST /api/disposal/submit
  if (pathname === '/api/disposal/submit' && method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const { username, imageHash, classification, coordinates } = JSON.parse(body);
        if (!username || !imageHash || !classification) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: "Missing required fields: username, imageHash, classification" }));
          return;
        }

        const result = dbHelper.submitDisposal(username, imageHash, classification, coordinates);
        if (!result.success) {
          res.writeHead(429, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: result.error, transaction: result.transaction }));
          return;
        }

        const transaction = result.transaction;

        // Broadcast initial submission event
        broadcast('citizen-event', {
          type: 'submission',
          username,
          classification,
          coordinates,
          transaction,
          timestamp: Date.now()
        });

        // Simulate client pipeline state transitions (Verification Pending -> Points Awarded/Rejected)
        const delay = 1500;
        setTimeout(() => {
          const approve = classification !== 'littered';
          const finalResult = dbHelper.finalizeVerification(transaction.id, approve);
          if (finalResult) {
            broadcast('citizen-event', {
              type: 'verification_completed',
              transaction: finalResult.transaction,
              user: finalResult.user,
              timestamp: Date.now()
            });
          }
        }, delay);

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          message: "Disposal registered. Pending verification.",
          transaction: transaction
        }));
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Invalid JSON format" }));
      }
    });
    return;
  }

  // POST /api/simulator/control
  if (pathname === '/api/simulator/control' && method === 'POST') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      try {
        const { action, rate } = JSON.parse(body);
        if (action === 'start') {
          simulator.start(rate || 120);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ message: "Simulator started", stats: simulator.getStats() }));
        } else if (action === 'stop') {
          simulator.stop();
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ message: "Simulator stopped", stats: simulator.getStats() }));
        } else if (action === 'rate') {
          simulator.updateRate(rate);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ message: `Simulator rate updated to ${rate}/min`, stats: simulator.getStats() }));
        } else {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: "Invalid action. Use 'start', 'stop', or 'rate'." }));
        }
      } catch (err) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: "Invalid JSON" }));
      }
    });
    return;
  }

  // POST /api/database/clear
  if (pathname === '/api/database/clear' && method === 'POST') {
    const state = dbHelper.clearDatabase();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ message: "Database reset successfully", state }));
    return;
  }

  // 3. STATIC FILE SERVING
  serveStaticFile(pathname, res);
});

// Initialize dummy user
dbHelper.getUser("citizen_zero");

// Start listening
server.listen(PORT, () => {
  console.log(`CleanMyCity unified server running on http://localhost:${PORT}`);
});
