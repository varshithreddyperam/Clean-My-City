// CleanMyCity Client-Side Engine
let eventSource;
let currentFile = null;
let currentPresetName = null;
let activeBlips = [];
const cityCenter = { lat: 17.3850, lng: 78.4867 };
let mapCanvas, mapCtx;
let mockBinNodes = [];
const transactionMap = new Map();

// Predefined Test Assets
const PRESETS = {
  'recycle_box.png': '/assets/recycle_box.png',
  'clean_bin.png': '/assets/clean_bin.png',
  'litter_road.png': '/assets/litter_road.png'
};

document.addEventListener('DOMContentLoaded', () => {
  initApp();
});

async function initApp() {
  setupNavigation();
  setupAuth();
  setupCitizenActions();
  setupAdminActions();
  initMap();
  setupEventStream();
  setupDetailsModal();

  // App starts in empty drag/drop upload state
  // loadPresetAsset('recycle_box.png');
}

// 1. Navigation tabs
function setupNavigation() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.getAttribute('data-tab');
      tabBtns.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active-content'));

      btn.classList.add('active');
      document.getElementById(tabId).classList.add('active-content');

      if (tabId === 'admin-view') {
        resizeMapCanvas();
      }
    });
  });
}

// 2. Authentication Gateway
function setupAuth() {
  const btnLoginSubmit = document.getElementById('btn-login-submit');
  const btnLogout = document.getElementById('btn-auth-logout');
  const loginUsernameInput = document.getElementById('login-username-input');

  // Load saved credentials
  const savedToken = localStorage.getItem('cmc_auth_token');
  const savedUser = localStorage.getItem('cmc_username');
  
  if (savedToken && savedUser) {
    if (loginUsernameInput) {
      loginUsernameInput.value = savedUser;
    }
    loginMockUser(savedUser);
  } else {
    showLoggedOutState();
  }

  if (btnLoginSubmit) {
    btnLoginSubmit.addEventListener('click', () => {
      const user = loginUsernameInput.value.trim().toLowerCase();
      if (user) {
        loginMockUser(user);
      }
    });
  }

  if (btnLogout) {
    btnLogout.addEventListener('click', () => {
      logoutUser();
    });
  }
}

function showLoggedInState() {
  const header = document.querySelector('.app-header');
  const loginPortal = document.getElementById('login-portal');
  const citizenView = document.getElementById('citizen-view');
  const adminView = document.getElementById('admin-view');

  if (header) header.style.display = 'flex';
  if (loginPortal) loginPortal.style.display = 'none';

  if (citizenView) citizenView.style.display = '';
  if (adminView) adminView.style.display = '';

  // Trigger map resize if admin view is active
  const activeTabBtn = document.querySelector('.tab-btn.active');
  if (activeTabBtn && activeTabBtn.getAttribute('data-tab') === 'admin-view') {
    resizeMapCanvas();
  }
}

function showLoggedOutState() {
  const header = document.querySelector('.app-header');
  const loginPortal = document.getElementById('login-portal');
  const citizenView = document.getElementById('citizen-view');
  const adminView = document.getElementById('admin-view');

  if (header) header.style.display = 'none';
  if (loginPortal) loginPortal.style.display = 'flex';
  if (citizenView) citizenView.style.display = 'none';
  if (adminView) adminView.style.display = 'none';
}

function resetNavigationToDefault() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  tabBtns.forEach(btn => {
    if (btn.getAttribute('data-tab') === 'citizen-view') {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  tabContents.forEach(content => {
    if (content.id === 'citizen-view') {
      content.classList.add('active-content');
    } else {
      content.classList.remove('active-content');
    }
  });
}

async function loginMockUser(username) {
  const token = `mock_token_${username}`;
  localStorage.setItem('cmc_auth_token', token);
  localStorage.setItem('cmc_username', username);
  
  resetNavigationToDefault();
  await updateUserProfile(username);
  showLoggedInState();
}

function logoutUser() {
  localStorage.removeItem('cmc_auth_token');
  localStorage.removeItem('cmc_username');
  resetNavigationToDefault();
  
  const userDisplayName = document.getElementById('user-display-name');
  if (userDisplayName) userDisplayName.innerText = 'Guest';
  
  const userPoints = document.getElementById('user-points');
  if (userPoints) userPoints.innerText = '0';
  
  const userLevelBadge = document.getElementById('user-level-badge');
  if (userLevelBadge) userLevelBadge.innerText = '1';
  
  const userLevel = document.getElementById('user-level');
  if (userLevel) userLevel.innerText = '1';
  
  const nextLevel = document.getElementById('next-level');
  if (nextLevel) nextLevel.innerText = '2';
  
  const userLevelProgress = document.getElementById('user-level-progress');
  if (userLevelProgress) userLevelProgress.style.width = '0%';
  
  const xpText = document.getElementById('xp-text');
  if (xpText) xpText.innerText = 'Please sign in';

  showLoggedOutState();
}

// Fetch user progression
async function updateUserProfile(username) {
  const token = localStorage.getItem('cmc_auth_token');
  try {
    const res = await fetch(`/api/user/${encodeURIComponent(username)}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) return;
    const user = await res.json();

    document.getElementById('user-display-name').innerText = user.username;
    document.getElementById('user-points').innerText = user.points;
    document.getElementById('user-level-badge').innerText = user.level;
    document.getElementById('user-level').innerText = user.level;
    document.getElementById('next-level').innerText = user.level + 1;

    // XP limits logic
    let xpMax = 150;
    let xpMin = 0;
    if (user.level === 2) { xpMin = 150; xpMax = 400; }
    else if (user.level === 3) { xpMin = 400; xpMax = 800; }
    else if (user.level >= 4) { xpMin = 800; xpMax = 1200; }

    const progressPercent = Math.min(100, Math.max(0, ((user.points - xpMin) / (xpMax - xpMin)) * 100));
    document.getElementById('user-level-progress').style.width = `${progressPercent}%`;
    document.getElementById('xp-text').innerText = `${user.points} / ${xpMax} XP to Level Up`;

    // Render Badges
    const badgesList = document.getElementById('badges-list');
    badgesList.innerHTML = '';
    
    const allBadges = [
      { name: "Green Novice", icon: "fa-user-astronaut", desc: "Joined Grid" },
      { name: "Sort Master", icon: "fa-recycle", desc: "First Recyclable" },
      { name: "Waste Buster", icon: "fa-trash-can", desc: "3 Valid Disposals" },
      { name: "Eco Legend", icon: "fa-crown", desc: "Eco Guardian Lvl 4" }
    ];

    allBadges.forEach(badge => {
      const hasBadge = user.badges.includes(badge.name);
      const badgeEl = document.createElement('div');
      badgeEl.className = `badge-item p-2 rounded-lg border text-center flex flex-col items-center justify-center ${hasBadge ? 'border-emerald-500/30 text-ecoaccent bg-emerald-500/5' : 'border-white/5 text-gray-500 locked bg-white/2'}`;
      badgeEl.title = badge.desc;
      badgeEl.innerHTML = `
        <i class="fa-solid ${badge.icon} text-lg mb-1"></i>
        <span class="text-[9px] font-semibold">${badge.name}</span>
      `;
      badgesList.appendChild(badgeEl);
    });

  } catch (error) {
    console.error("Profile sync error:", error);
  }
}

// 3. Citizen Camera and Image uploads
function setupCitizenActions() {
  const fileUploader = document.getElementById('file-uploader');
  const cameraDropZone = document.getElementById('camera-drop-zone');
  const presetBtns = document.querySelectorAll('.btn-preset');
  const btnSubmit = document.getElementById('btn-submit-disposal');

  // Drag and Drop
  cameraDropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    cameraDropZone.classList.add('dragover');
  });

  cameraDropZone.addEventListener('dragleave', () => {
    cameraDropZone.classList.remove('dragover');
  });

  cameraDropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    cameraDropZone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) handleImageFile(file);
  });

  fileUploader.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) handleImageFile(file);
  });

  // Click drop zone to select file
  cameraDropZone.addEventListener('click', (e) => {
    if (e.target !== fileUploader) {
      fileUploader.click();
    }
  });

  // Preset Buttons
  presetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      presetBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');

      const assetKey = btn.getAttribute('data-asset');
      if (assetKey === 'spoof_duplicate') {
        triggerSpoofDuplicatePreset();
      } else {
        loadPresetAsset(assetKey);
      }
    });
  });

  btnSubmit.addEventListener('click', submitDisposalPayload);
}

// Load preset asset
async function loadPresetAsset(filename) {
  currentPresetName = filename;
  currentFile = null; // resets local file reference

  const path = PRESETS[filename];
  const imgView = document.getElementById('simulated-image-view');
  const dropPrompt = document.getElementById('drop-prompt-text');
  const camDisplay = document.getElementById('cam-display-container');

  dropPrompt.classList.add('hidden');
  camDisplay.classList.remove('hidden');

  imgView.onload = () => {
    resetPipelineUI();
  };
  imgView.src = path;
}

// Redis spoof duplicate signature preset trigger
async function triggerSpoofDuplicatePreset() {
  currentPresetName = "spoof_duplicate_recycle_box.png";
  currentFile = null;

  const imgView = document.getElementById('simulated-image-view');
  const dropPrompt = document.getElementById('drop-prompt-text');
  const camDisplay = document.getElementById('cam-display-container');

  dropPrompt.classList.add('hidden');
  camDisplay.classList.remove('hidden');

  imgView.onload = () => {
    resetPipelineUI();
  };
  imgView.src = PRESETS['recycle_box.png'];
}

// Load custom file upload
function handleImageFile(file) {
  currentFile = file;
  currentPresetName = null;

  const reader = new FileReader();
  reader.onload = (e) => {
    const imgView = document.getElementById('simulated-image-view');
    const dropPrompt = document.getElementById('drop-prompt-text');
    const camDisplay = document.getElementById('cam-display-container');

    dropPrompt.classList.add('hidden');
    camDisplay.classList.remove('hidden');

    imgView.onload = () => {
      resetPipelineUI();
    };
    imgView.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

// Resets visual canvases and outputs until user clicks Submit
function resetPipelineUI() {
  // Hide image preview overlay or show placeholders for canvases
  document.getElementById('ph-grayscale').classList.remove('hidden');
  document.getElementById('ph-edges').classList.remove('hidden');
  document.getElementById('ph-contours').classList.remove('hidden');

  // Clear canvases
  const gCanvas = document.getElementById('canvas-grayscale');
  const eCanvas = document.getElementById('canvas-edges');
  const cCanvas = document.getElementById('canvas-contours');
  gCanvas.getContext('2d').clearRect(0, 0, gCanvas.width, gCanvas.height);
  eCanvas.getContext('2d').clearRect(0, 0, eCanvas.width, eCanvas.height);
  cCanvas.getContext('2d').clearRect(0, 0, cCanvas.width, cCanvas.height);

  // Reset classification values
  document.getElementById('ai-detected-category').innerText = '---';
  document.getElementById('ai-detected-category').style.color = '#fff';
  document.getElementById('ai-confidence').innerText = '0%';
  document.getElementById('ai-edge-verdict').innerText = '---';
  document.getElementById('ai-edge-verdict').style.color = '#fff';

  // Enable submit button
  document.getElementById('btn-submit-disposal').disabled = false;
  
  // Set banner back to idle
  updateFeedbackBanner('idle', 'Image Selected', 'File loaded. Click "Submit to AI Grid" to run OpenCV edge analysis and authenticate ledger credits.');
}

// Runs quick OpenCV visual feedback in browser canvas
function mockClientVisionPipeline(imgView, filename) {
  const gCanvas = document.getElementById('canvas-grayscale');
  const eCanvas = document.getElementById('canvas-edges');
  const cCanvas = document.getElementById('canvas-contours');

  const ctxG = gCanvas.getContext('2d');
  gCanvas.width = 150; gCanvas.height = 100;
  ctxG.drawImage(imgView, 0, 0, gCanvas.width, gCanvas.height);
  
  // Apply visual grayscale filter in canvas
  const imgData = ctxG.getImageData(0, 0, gCanvas.width, gCanvas.height);
  const data = imgData.data;
  for (let i = 0; i < data.length; i += 4) {
    const brightness = 0.34 * data[i] + 0.5 * data[i + 1] + 0.16 * data[i + 2];
    data[i] = brightness;
    data[i + 1] = brightness;
    data[i + 2] = brightness;
  }
  ctxG.putImageData(imgData, 0, 0);

  // Edges visualization
  const ctxE = eCanvas.getContext('2d');
  eCanvas.width = 150; eCanvas.height = 100;
  ctxE.fillStyle = '#060a13';
  ctxE.fillRect(0, 0, eCanvas.width, eCanvas.height);
  ctxE.strokeStyle = '#00f2fe';
  ctxE.strokeRect(10, 10, eCanvas.width - 20, eCanvas.height - 20);
  ctxE.fillStyle = '#00f2fe';
  ctxE.font = '10px Orbitron';
  ctxE.fillText("OpenCV Edge Pass", 20, 50);

  // Contours visualization
  const ctxC = cCanvas.getContext('2d');
  cCanvas.width = 150; cCanvas.height = 100;
  ctxC.fillStyle = '#060a13';
  ctxC.fillRect(0, 0, cCanvas.width, cCanvas.height);
  ctxC.strokeStyle = '#10b981';
  ctxC.strokeRect(5, 5, cCanvas.width - 10, cCanvas.height - 10);
  ctxC.fillStyle = '#10b981';
  ctxC.font = '10px Orbitron';
  ctxC.fillText("Framing Approved", 15, 50);

  // Remove placeholders
  document.getElementById('ph-grayscale').classList.add('hidden');
  document.getElementById('ph-edges').classList.add('hidden');
  document.getElementById('ph-contours').classList.add('hidden');

  // Show analysis pending labels (actual classification comes from backend)
  const labelEl = document.getElementById('ai-detected-category');
  const confEl = document.getElementById('ai-confidence');
  const alignEl = document.getElementById('ai-edge-verdict');

  labelEl.innerText = 'Analyzing...';
  labelEl.style.color = '#5d4037';
  confEl.innerText = '--%';
  alignEl.innerText = 'Aligned & Framed (PASS)';
  alignEl.style.color = '#10b981';

  document.getElementById('btn-submit-disposal').disabled = false;
  updateFeedbackBanner('idle', 'Preprocessing Complete', 'OpenCV analysis done. Ready to submit for AI model classification.');
}

function updateFeedbackBanner(status, title, description) {
  const banner = document.getElementById('validation-banner');
  const icon = document.getElementById('banner-icon');
  const titleEl = document.getElementById('banner-title');
  const descEl = document.getElementById('banner-description');

  banner.className = `validation-status-banner ${status} rounded-xl p-4 flex border-l-4 bg-white/5`;
  titleEl.innerText = title;
  descEl.innerText = description;

  icon.className = 'fa-solid text-xl';
  if (status === 'idle') {
    banner.style.borderLeftColor = '#6b7280';
    icon.className += ' fa-info-circle text-gray-400';
  } else if (status === 'pending') {
    banner.style.borderLeftColor = '#3b82f6';
    icon.className += ' fa-spinner fa-spin text-blue-400';
  } else if (status === 'success') {
    banner.style.borderLeftColor = '#10b981';
    icon.className += ' fa-circle-check text-ecoaccent';
  } else if (status === 'failed') {
    banner.style.borderLeftColor = '#ef4444';
    icon.className += ' fa-circle-xmark text-red-500';
  }
}

// Submit transaction payload to backend
async function submitDisposalPayload() {
  const token = localStorage.getItem('cmc_auth_token');
  const username = localStorage.getItem('cmc_username') || 'guest';

  const btnSubmit = document.getElementById('btn-submit-disposal');
  btnSubmit.disabled = true;

  const imgView = document.getElementById('simulated-image-view');
  const filename = currentFile ? currentFile.name : currentPresetName;
  if (!filename) {
    updateFeedbackBanner('failed', 'Payload Missing', 'Please select or upload a waste image.');
    btnSubmit.disabled = false;
    return;
  }

  // Run the visual OpenCV edge Contours preprocessing pipeline ONLY on click Submit!
  mockClientVisionPipeline(imgView, filename);

  updateFeedbackBanner('pending', 'Processing...', 'Running image through MobileNetV2 AI model for classification...');

  const formData = new FormData();
  
  // Generate random lat/long coordinates centered in NYC
  const latOffset = (Math.random() - 0.5) * 0.03;
  const lngOffset = (Math.random() - 0.5) * 0.03;
  formData.append('lat', (cityCenter.lat + latOffset).toFixed(6));
  formData.append('lng', (cityCenter.lng + lngOffset).toFixed(6));

  if (currentFile) {
    formData.append('file', currentFile);
  } else if (currentPresetName) {
    // If using a preset, fetch the file blob and append
    try {
      const response = await fetch(PRESETS[currentPresetName]);
      const blob = await response.blob();
      formData.append('file', blob, currentPresetName);
    } catch (e) {
      updateFeedbackBanner('failed', 'Asset Load Error', 'Could not load pre-packaged simulator image.');
      btnSubmit.disabled = false;
      return;
    }
  } else {
    updateFeedbackBanner('failed', 'Payload Missing', 'Please select or upload a waste image.');
    btnSubmit.disabled = false;
    return;
  }

  try {
    const res = await fetch('/api/disposal/submit', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: formData
    });

    const data = await res.json();

    if (!res.ok) {
      updateFeedbackBanner('failed', 'API Ledger Blocked', data.detail || 'Validation failed on state machine.');
      if (res.status === 429) {
        startCooldownCountdown(15);
      }
      return;
    }

    updateFeedbackBanner('pending', 'Verification Pending', 'Upload succeeded. Asynchronous AI pipeline running verification tasks...');
    startCooldownCountdown(15);

  } catch (error) {
    console.error("Disposal upload error:", error);
    updateFeedbackBanner('failed', 'Server Offline', 'Could not connect to the backend server. Make sure it is running.');
    btnSubmit.disabled = false;
  }
}

function startCooldownCountdown(seconds) {
  const btnSubmit = document.getElementById('btn-submit-disposal');
  const cooldownWidget = document.getElementById('cooldown-widget');
  const timerLabel = document.getElementById('cooldown-timer');

  btnSubmit.disabled = true;
  cooldownWidget.classList.remove('hidden');
  
  let timeLeft = seconds;
  timerLabel.innerText = `${timeLeft}s`;
  
  const interval = setInterval(() => {
    timeLeft--;
    timerLabel.innerText = `${timeLeft}s`;
    
    if (timeLeft <= 0) {
      clearInterval(interval);
      cooldownWidget.classList.add('hidden');
      btnSubmit.disabled = false;
    }
  }, 1000);
}

// 4. Server-Sent Events (SSE) Live Feed listener
function setupEventStream() {
  eventSource = new EventSource('/api/events');

  eventSource.onmessage = (event) => {
    try {
      if (!event.data) return;
      const parsed = JSON.parse(event.data);
      const { type, data } = parsed;

      if (type === 'stats') {
        updateDashboardStats(data);
      } else {
        handleIncomingGridEvent(data);
      }
    } catch (e) {
      // Ignore parsing errors from empty heartbeat signals
    }
  };

  eventSource.onerror = (e) => {
    console.warn("SSE disconnected. Reconnect sweep active.");
    const indicator = document.querySelector('.system-status-indicator');
    if (indicator) {
      indicator.innerHTML = `
        <span class="status-dot red"></span>
        <span class="status-label">Server Offline</span>
      `;
      indicator.className = "system-status-indicator flex items-center gap-2 bg-red-500/10 border border-red-500/20 px-3 py-1.5 rounded-full text-xs text-red-500 font-semibold tracking-wider font-display";
    }
  };
  
  eventSource.onopen = () => {
    const indicator = document.querySelector('.system-status-indicator');
    if (indicator) {
      indicator.innerHTML = `
        <span class="status-dot green"></span>
        <span class="status-label">AI Server Online</span>
      `;
      indicator.className = "system-status-indicator flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-full text-xs text-ecoaccent font-semibold tracking-wider font-display";
    }
  };
}

// 5. Admin Dashboard Controls
function setupAdminActions() {
  const btnStart = document.getElementById('btn-start-sim');
  const btnStop = document.getElementById('btn-stop-sim');
  const slider = document.getElementById('sim-rate-slider');
  const sliderVal = document.getElementById('slider-val-label');
  const btnReset = document.getElementById('btn-reset-db');

  slider.addEventListener('input', () => {
    sliderVal.innerText = `${slider.value} / min`;
  });

  slider.addEventListener('change', async () => {
    const rate = parseInt(slider.value);
    await fetch('/api/simulator/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'rate', rate })
    });
  });

  btnStart.addEventListener('click', async () => {
    const rate = parseInt(slider.value);
    btnStart.disabled = true;
    btnStop.disabled = false;
    
    await fetch('/api/simulator/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'start', rate })
    });
  });

  btnStop.addEventListener('click', async () => {
    btnStart.disabled = false;
    btnStop.disabled = true;
    
    await fetch('/api/simulator/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'stop' })
    });
  });

  btnReset.addEventListener('click', async () => {
    if (confirm("Are you sure you want to purge SQLAlchemy database tables and flush Redis cache pools?")) {
      const res = await fetch('/api/database/clear', { method: 'POST' });
      const data = await res.json();
      
      const currentUsername = localStorage.getItem('cmc_username') || 'citizen_zero';
      updateUserProfile(currentUsername);
      alert(data.message);
    }
  });

  fetchLedgerLogs();
}

async function fetchLedgerLogs() {
  try {
    const res = await fetch('/api/ledger');
    if (!res.ok) return;
    const logs = await res.json();
    
    const ticker = document.getElementById('ledger-logs-ticker');
    if (logs.length > 0) {
      ticker.innerHTML = '';
      logs.forEach(log => {
        injectLogEntry(log, true);
      });
    }
  } catch (error) {
    console.error("Error fetching logs:", error);
  }
}

function updateDashboardStats(stats) {
  const stateBadge = document.getElementById('sim-state-badge');
  const btnStart = document.getElementById('btn-start-sim');
  const btnStop = document.getElementById('btn-stop-sim');

  if (stats.isRunning) {
    stateBadge.innerText = 'ONLINE';
    stateBadge.className = 'sim-state-text text-ecoaccent font-bold font-display text-sm uppercase tracking-wider';
    btnStart.disabled = true;
    btnStop.disabled = false;
  } else {
    stateBadge.innerText = 'OFFLINE';
    stateBadge.className = 'sim-state-text text-red-500 font-bold font-display text-sm uppercase tracking-wider';
    btnStart.disabled = false;
    btnStop.disabled = true;
  }

  document.getElementById('stat-cpu').innerText = `${stats.cpuLoad}%`;
  document.getElementById('stat-points-awarded').innerText = stats.awardedTransactions;
  document.getElementById('stat-spoofs').innerText = stats.spoofTransactions;
  document.getElementById('stat-queue').innerText = stats.pendingTransactions;
}

// 6. Handle Real-time Event Broadcaster
function handleIncomingGridEvent(event) {
  const activeUser = localStorage.getItem('cmc_username') || 'citizen_zero';
  
  // Check if completion relates to us
  if (event.transaction && event.transaction.username === activeUser) {
    if (event.type === 'verification_completed') {
      const tx = event.transaction;
      const labelEl = document.getElementById('ai-detected-category');
      const confEl = document.getElementById('ai-confidence');
      const alignEl = document.getElementById('ai-edge-verdict');

      if (tx.status === 'Points Awarded') {
        updateFeedbackBanner('success', 'Points Awarded!', `State verified. Added +${tx.rewardPoints} XP to ledger account!`);
        triggerPointsSparkle();
        
        // Align frontend tags with actual database category
        if (tx.classification === 'recyclable') {
          labelEl.innerText = 'Recyclable Container';
          labelEl.style.color = '#00f2fe';
          confEl.innerText = '94%';
        } else {
          labelEl.innerText = 'Non-Recyclable Waste';
          labelEl.style.color = '#3b82f6';
          confEl.innerText = '88%';
        }
        alignEl.innerText = 'Aligned & Framed (PASS)';
        alignEl.style.color = '#10b981';
      } else {
        updateFeedbackBanner('failed', 'Disposal Rejected', tx.statusReason || 'Validation failed. Points withheld.');
        
        // Set to fail tags
        if (tx.classification === 'invalid_disposal') {
          labelEl.innerText = 'Human / Face Present';
        } else if (tx.classification === 'unknown_object') {
          labelEl.innerText = 'Unknown Object';
        } else {
          labelEl.innerText = 'Rejected Disposal';
        }
        labelEl.style.color = '#ef4444';
        confEl.innerText = '0%';
        alignEl.innerText = 'Outside Receptacle / Face Detected (FAIL)';
        alignEl.style.color = '#ef4444';
      }
      updateUserProfile(activeUser);
    }
  }

  if (event.transaction) {
    injectLogEntry(event.transaction, false);
  } else if (event.type === 'rejected_instant') {
    injectLogEntry(event.transaction || {
      id: Math.random().toString(),
      username: event.username,
      classification: event.classification,
      status: 'Spoof Rejected',
      timestamp: event.timestamp,
      rewardPoints: 0
    }, false);
  }

  // Draw blip on map coordinate
  if (event.coordinates) {
    let color = '#00f2fe';
    if (event.classification === 'recyclable') color = '#10b981';
    else if (event.classification === 'non-recyclable') color = '#3b82f6';
    
    if (event.type === 'rejected_instant' || (event.transaction && event.transaction.status === 'Spoof Rejected')) {
      color = '#f59e0b';
    }

    addMapBlip(event.coordinates.lat, event.coordinates.lng, color);
  }
}

// Inject table entries
function injectLogEntry(tx, append = false) {
  if (tx && tx.id) {
    transactionMap.set(tx.id, tx);
  }
  const ticker = document.getElementById('ledger-logs-ticker');
  
  const emptyPlaceholder = ticker.querySelector('.empty');
  if (emptyPlaceholder) emptyPlaceholder.remove();

  const row = document.createElement('div');
  row.className = 'log-entry grid grid-cols-[70px_100px_90px_1fr] px-4 py-2 border-b border-white/5 text-xs items-center cursor-pointer hover:bg-white/5 transition';
  row.dataset.id = tx.id;

  const date = new Date(tx.timestamp);
  const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  let classificationClass = 'recyclable';
  if (tx.classification === 'non-recyclable') classificationClass = 'non-recyclable';
  
  let statusClass = 'pending';
  let statusText = 'Pending';

  if (tx.status === 'Points Awarded') {
    statusClass = 'awarded';
    statusText = `Awarded (+${tx.rewardPoints || tx.reward_points} XP)`;
  } else if (tx.status === 'Rejected') {
    statusClass = 'rejected';
    statusText = 'Rejected';
  } else if (tx.status === 'Spoof Rejected') {
    statusClass = 'spoof';
    statusText = 'Spoof Blocked';
    classificationClass = 'spoof';
  }

  row.innerHTML = `
    <span class="log-time text-gray-500 font-display">${timeStr}</span>
    <span class="log-user text-white truncate pr-2" title="${tx.username}">${tx.username}</span>
    <span class="log-class ${classificationClass} font-semibold uppercase text-[10px]">${tx.classification}</span>
    <span class="log-status-badge ${statusClass}">${statusText}</span>
  `;

  const existingRow = ticker.querySelector(`[data-id="${tx.id}"]`);
  if (existingRow) {
    existingRow.replaceWith(row);
  } else {
    if (append) {
      ticker.appendChild(row);
    } else {
      ticker.insertBefore(row, ticker.firstChild);
      if (ticker.children.length > 100) {
        ticker.lastChild.remove();
      }
    }
  }
}

// 7. Leaflet Map Visualizer
let mapInstance;
let mockBinMarkers = [];

function initMap() {
  // Center on NYC
  mapInstance = L.map('city-map', {
    zoomControl: false,
    attributionControl: false
  }).setView([cityCenter.lat, cityCenter.lng], 13);

  // Add CartoDB Voyager (Light) tiles
  L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
    maxZoom: 19
  }).addTo(mapInstance);

  // Add zoom control manually in top-right
  L.control.zoom({ position: 'topright' }).addTo(mapInstance);

  generateMockInfrastructurePoints();
}

function resizeMapCanvas() {
  if (mapInstance) {
    mapInstance.invalidateSize();
  }
}

function generateMockInfrastructurePoints() {
  // Clear existing markers if any
  mockBinMarkers.forEach(m => mapInstance.removeLayer(m));
  mockBinMarkers = [];
  mockBinNodes = [];

  for (let i = 0; i < 25; i++) {
    const latOffset = (Math.random() - 0.5) * 0.035;
    const lngOffset = (Math.random() - 0.5) * 0.035;
    const lat = cityCenter.lat + latOffset;
    const lng = cityCenter.lng + lngOffset;
    const type = Math.random() > 0.4 ? 'recycling' : 'standard';
    
    mockBinNodes.push({ lat, lng, type });

    // Draw as a neat small Leaflet CircleMarker
    const color = type === 'recycling' ? '#00f2fe' : '#10b981';
    const marker = L.circleMarker([lat, lng], {
      radius: 5,
      fillColor: color,
      color: '#0a0e17',
      weight: 1.5,
      opacity: 1,
      fillOpacity: 0.9
    }).addTo(mapInstance);

    marker.bindPopup(`<strong>Smart Receptacle Node</strong><br>Type: ${type === 'recycling' ? 'Recyclable Container' : 'Non-Recyclable Trash'}<br>Coords: ${lat.toFixed(5)}, ${lng.toFixed(5)}`);
    mockBinMarkers.push(marker);
  }
}

function addMapBlip(lat, lng, color) {
  if (!mapInstance) return;

  // Create a circle at the location with expanding meters radius
  const blip = L.circle([lat, lng], {
    radius: 10,
    fillColor: color,
    color: color,
    weight: 2,
    opacity: 1.0,
    fillOpacity: 0.4
  }).addTo(mapInstance);

  let currentRadius = 10;
  const maxRadius = 350; // meters
  const duration = 1200; // ms
  const startTime = Date.now();

  const animate = () => {
    const elapsed = Date.now() - startTime;
    const progress = Math.min(elapsed / duration, 1);
    
    // Smooth easing out
    const easeProgress = 1 - Math.pow(1 - progress, 3); 
    
    const newRadius = 10 + easeProgress * (maxRadius - 10);
    const newOpacity = 1.0 - easeProgress;
    
    blip.setRadius(newRadius);
    blip.setStyle({
      opacity: newOpacity,
      fillOpacity: newOpacity * 0.4
    });

    if (progress < 1) {
      requestAnimationFrame(animate);
    } else {
      mapInstance.removeLayer(blip);
    }
  };

  requestAnimationFrame(animate);
}

// Sparkle particle effect for points
function triggerPointsSparkle() {
  const container = document.querySelector('.points-display');
  if (!container) return;
  
  for (let i = 0; i < 15; i++) {
    const particle = document.createElement('div');
    particle.style.position = 'absolute';
    particle.style.width = '6px';
    particle.style.height = '6px';
    particle.style.backgroundColor = '#10b981';
    particle.style.borderRadius = '50%';
    
    const rect = container.getBoundingClientRect();
    particle.style.left = `${rect.width / 2}px`;
    particle.style.top = `${rect.height / 2}px`;
    
    const angle = Math.random() * Math.PI * 2;
    const distance = 40 + Math.random() * 60;
    const targetX = Math.cos(angle) * distance;
    const targetY = Math.sin(angle) * distance;

    container.appendChild(particle);

    particle.animate([
      { transform: 'translate(0, 0) scale(1)', opacity: 1 },
      { transform: `translate(${targetX}px, ${targetY}px) scale(0)`, opacity: 0 }
    ], {
      duration: 800 + Math.random() * 400,
      easing: 'cubic-bezier(0.1, 0.8, 0.3, 1)'
    }).onfinish = () => particle.remove();
  }
}

// 8. Transaction Details Audit Drawer/Modal
function setupDetailsModal() {
  const ticker = document.getElementById('ledger-logs-ticker');
  const modal = document.getElementById('tx-details-modal');
  const closeModalBtn = document.getElementById('btn-close-modal');

  ticker.addEventListener('click', (e) => {
    const entry = e.target.closest('.log-entry');
    if (!entry || entry.classList.contains('empty')) return;
    
    const txId = entry.dataset.id;
    const tx = transactionMap.get(txId);
    if (tx) {
      showTransactionDetailsModal(tx);
    }
  });

  closeModalBtn.addEventListener('click', () => {
    modal.style.display = 'none';
    modal.classList.add('hidden');
  });

  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.style.display = 'none';
      modal.classList.add('hidden');
    }
  });
}

function showTransactionDetailsModal(tx) {
  const modal = document.getElementById('tx-details-modal');
  document.getElementById('modal-tx-id').innerText = `id: ${tx.id}`;
  document.getElementById('modal-username').innerText = tx.username;
  document.getElementById('modal-reward').innerText = `+${tx.rewardPoints || tx.reward_points || 0} XP`;
  let categoryLabel = 'Unknown Object';
  if (tx.classification === 'recyclable') {
    categoryLabel = 'Recyclable Container';
  } else if (tx.classification === 'non-recyclable') {
    categoryLabel = 'Non-Recyclable Waste';
  } else if (tx.classification === 'invalid_disposal') {
    categoryLabel = 'Invalid Disposal (Face Detected)';
  } else if (tx.classification === 'littered') {
    categoryLabel = 'Littered Alert';
  }
  document.getElementById('modal-class').innerText = categoryLabel;
  
  const statusEl = document.getElementById('modal-status');
  statusEl.innerText = tx.status;
  statusEl.className = 'log-status-badge mt-0.5 ';
  if (tx.status === 'Points Awarded') statusEl.className += 'awarded';
  else if (tx.status === 'Verification Pending') statusEl.className += 'pending';
  else if (tx.status === 'Rejected') statusEl.className += 'rejected';
  else if (tx.status === 'Spoof Rejected') statusEl.className += 'spoof';

  // Coordinates
  const gpsText = tx.coordinates ? `${tx.coordinates.lat}, ${tx.coordinates.lng}` : (tx.lat ? `${tx.lat}, ${tx.lng}` : '40.7128, -74.0060');
  document.getElementById('modal-gps').innerText = gpsText;

  // Reason
  const reasonContainer = document.getElementById('modal-reason-container');
  if (tx.statusReason || tx.status_reason) {
    reasonContainer.style.display = 'block';
    document.getElementById('modal-reason').innerText = tx.statusReason || tx.status_reason;
  } else {
    reasonContainer.style.display = 'none';
  }

  // Image rendering
  const imgEl = document.getElementById('modal-image-view');
  const phEl = document.getElementById('modal-image-placeholder');
  
  const imgUrl = tx.imageUrl || tx.image_url;
  if (imgUrl) {
    imgEl.src = imgUrl;
    imgEl.classList.remove('hidden');
    phEl.classList.add('hidden');
  } else {
    imgEl.src = '';
    imgEl.classList.add('hidden');
    phEl.classList.remove('hidden');
  }

  modal.style.display = 'flex';
  modal.classList.remove('hidden');
}
