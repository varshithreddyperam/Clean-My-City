const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DATA_DIR = path.join(__dirname, 'data');
const DB_FILE = path.join(DATA_DIR, 'ledger.json');

// Default initial state
const defaultDb = {
  users: {
    "citizen_zero": {
      username: "citizen_zero",
      points: 120,
      level: 1,
      badges: ["Green Novice"],
      lastSubmissionTime: 0
    }
  },
  ledger: []
};

// Ensure data directory and file exist
function initializeDb() {
  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }
  if (!fs.existsSync(DB_FILE)) {
    fs.writeFileSync(DB_FILE, JSON.stringify(defaultDb, null, 2), 'utf-8');
  }
}

function readDb() {
  initializeDb();
  try {
    const data = fs.readFileSync(DB_FILE, 'utf-8');
    return JSON.parse(data);
  } catch (error) {
    console.error("Error reading database file, using fallback:", error);
    return defaultDb;
  }
}

function writeDb(db) {
  try {
    fs.writeFileSync(DB_FILE, JSON.stringify(db, null, 2), 'utf-8');
  } catch (error) {
    console.error("Error writing database file:", error);
  }
}

const dbHelper = {
  getUser(username) {
    const db = readDb();
    const cleanUsername = username.trim().toLowerCase();
    if (!db.users[cleanUsername]) {
      db.users[cleanUsername] = {
        username: cleanUsername,
        points: 0,
        level: 1,
        badges: ["Green Novice"],
        lastSubmissionTime: 0
      };
      writeDb(db);
    }
    return db.users[cleanUsername];
  },

  getAllUsers() {
    const db = readDb();
    return Object.values(db.users).sort((a, b) => b.points - a.points);
  },

  getLedger() {
    const db = readDb();
    return db.ledger;
  },

  calculateLevel(points) {
    if (points >= 800) return 4;
    if (points >= 400) return 3;
    if (points >= 150) return 2;
    return 1;
  },

  checkBadges(user, ledger) {
    const badges = [...user.badges];
    const userSubmissions = ledger.filter(item => item.username === user.username && item.status === 'Points Awarded');
    
    // Sort Master badge - first recyclable
    if (!badges.includes("Sort Master")) {
      const hasRecyclable = userSubmissions.some(item => item.classification === 'recyclable');
      if (hasRecyclable) {
        badges.push("Sort Master");
      }
    }

    // Litter Buster badge - 3 successful clean disposals
    if (!badges.includes("Litter Buster")) {
      const cleanDisposalsCount = userSubmissions.filter(item => item.classification === 'recyclable' || item.classification === 'non-recyclable').length;
      if (cleanDisposalsCount >= 3) {
        badges.push("Litter Buster");
      }
    }

    // Eco Legend badge - level 4
    if (!badges.includes("Eco Legend") && user.level >= 4) {
      badges.push("Eco Legend");
    }

    return badges;
  },

  submitDisposal(username, imageHash, classification, coordinates) {
    const db = readDb();
    const cleanUsername = username.trim().toLowerCase();
    const user = this.getUser(cleanUsername); // Ensure user exists
    
    const now = Date.now();
    const COOLDOWN_MS = 15 * 1000; // 15 seconds cooldown for demo/testing
    const SPOOF_CHECK_MS = 60 * 1000; // 1 minute spoof window

    // 1. Cooldown validation
    const timeSinceLast = now - user.lastSubmissionTime;
    if (user.lastSubmissionTime > 0 && timeSinceLast < COOLDOWN_MS) {
      const secondsLeft = Math.ceil((COOLDOWN_MS - timeSinceLast) / 1000);
      return {
        success: false,
        error: `Submission blocked. Cooldown active. Please wait ${secondsLeft} seconds.`
      };
    }

    // 2. Duplicate submission spoofing check
    // If the exact same imageHash has been submitted in the last minute, reject it
    const isDuplicate = db.ledger.some(item => 
      item.imageHash === imageHash && 
      (now - item.timestamp) < SPOOF_CHECK_MS
    );
    if (isDuplicate) {
      const submissionId = crypto.randomUUID();
      const duplicateEntry = {
        id: submissionId,
        username: cleanUsername,
        imageHash: imageHash,
        classification: classification,
        coordinates: coordinates || { lat: 0, lng: 0 },
        status: 'Spoof Rejected',
        statusReason: 'Duplicate image hash detected (Anti-Spoofing)',
        timestamp: now,
        rewardPoints: 0
      };
      db.ledger.unshift(duplicateEntry);
      writeDb(db);
      return {
        success: false,
        error: "Spoofing attempt detected. Duplicate disposal signature blocked.",
        transaction: duplicateEntry
      };
    }

    // 3. Process Valid Submission (Initial State: Verification Pending)
    const submissionId = crypto.randomUUID();
    let rewardPoints = 0;

    // Reject littered/dirty inputs
    if (classification === 'littered') {
      const rejectEntry = {
        id: submissionId,
        username: cleanUsername,
        imageHash: imageHash,
        classification: classification,
        coordinates: coordinates || { lat: 0, lng: 0 },
        status: 'Verification Pending', // Starts here
        timestamp: now,
        rewardPoints: 0
      };
      db.ledger.unshift(rejectEntry);
      
      // Update cooldown timestamp even for failed attempts to prevent spam
      db.users[cleanUsername].lastSubmissionTime = now;
      writeDb(db);
      return {
        success: true,
        status: 'Pending',
        transaction: rejectEntry
      };
    }

    // Assign points for correct disposal
    if (classification === 'recyclable') {
      rewardPoints = 50;
    } else if (classification === 'non-recyclable') {
      rewardPoints = 20;
    }

    const transactionEntry = {
      id: submissionId,
      username: cleanUsername,
      imageHash: imageHash,
      classification: classification,
      coordinates: coordinates || { lat: 0, lng: 0 },
      status: 'Verification Pending',
      timestamp: now,
      rewardPoints: rewardPoints
    };

    db.ledger.unshift(transactionEntry);
    db.users[cleanUsername].lastSubmissionTime = now;
    writeDb(db);

    return {
      success: true,
      status: 'Pending',
      transaction: transactionEntry
    };
  },

  finalizeVerification(transactionId, approve) {
    const db = readDb();
    const transaction = db.ledger.find(item => item.id === transactionId);
    if (!transaction || transaction.status !== 'Verification Pending') {
      return null;
    }

    const username = transaction.username;
    const user = db.users[username];

    if (approve && transaction.classification !== 'littered') {
      transaction.status = 'Points Awarded';
      user.points += transaction.rewardPoints;
      user.level = this.calculateLevel(user.points);
      user.badges = this.checkBadges(user, db.ledger);
    } else {
      transaction.status = 'Rejected';
      transaction.statusReason = transaction.classification === 'littered' 
        ? 'Littering detected: Trash not properly placed inside container.' 
        : 'Image verification failed (low confidence or bad lighting)';
      transaction.rewardPoints = 0;
    }

    writeDb(db);
    return {
      transaction,
      user
    };
  },

  clearDatabase() {
    writeDb(defaultDb);
    return defaultDb;
  }
};

module.exports = dbHelper;
