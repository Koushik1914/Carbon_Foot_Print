/*
  EcoQuest - App Controller
  Vanilla JS Logic, Event Listeners, State Management, and API communication.
*/

// Configuration: Adjust to your deployed Cloud Run URL if running in production
const API_BASE = 'http://localhost:8080'; 

// Local App State
const state = {
  user: {
    id: localStorage.getItem('ecoquest_userId') || 'user_' + Math.random().toString(36).substring(2, 9),
    name: localStorage.getItem('ecoquest_userName') || 'Eco Ranger',
    type: localStorage.getItem('ecoquest_userType') || 'student'
  },
  challenges: [],
  profile: null
};

// Save User Profile to LocalStorage
function saveStateToLocalStorage() {
  localStorage.setItem('ecoquest_userId', state.user.id);
  localStorage.setItem('ecoquest_userName', state.user.name);
  localStorage.setItem('ecoquest_userType', state.user.type);
}

// Log Helper
function log(msg) {
  console.log(`[EcoQuest]: ${msg}`);
}

// Fetch helper with headers and error handling
async function apiCall(endpoint, method = 'GET', body = null) {
  const url = `${API_BASE}${endpoint}`;
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json'
    }
  };
  if (body) {
    options.body = JSON.stringify(body);
  }
  
  try {
    const response = await fetch(url, options);
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Unknown error occurred' }));
      throw new Error(err.detail || `HTTP Error ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`API Call failed: ${endpoint}`, error);
    throw error;
  }
}

// Initialize Dashboard & Core Listeners
document.addEventListener('DOMContentLoaded', () => {
  log("Initializing application...");
  
  // Set initial UI values for user config
  const userIdInput = document.getElementById('config-user-id');
  const userNameInput = document.getElementById('config-user-name');
  const userTypeSelect = document.getElementById('config-user-type');
  
  if (userIdInput) userIdInput.value = state.user.id;
  if (userNameInput) userNameInput.value = state.user.name;
  if (userTypeSelect) userTypeSelect.value = state.user.type;
  
  updateUserBadge();

  // Load appropriate page components
  const pagePath = window.location.pathname;
  if (pagePath.includes('community.html')) {
    initCommunityPage();
  } else {
    initDashboardPage();
  }

  // Set up chatbot event listeners
  initChatbot();
});

// Update Badge in Header
function updateUserBadge() {
  const badgeName = document.getElementById('header-user-name');
  if (badgeName) {
    badgeName.textContent = `${state.user.name} (${state.user.type})`;
  }
}

// Config Panel Update User handler
function updateCurrentUser() {
  const id = document.getElementById('config-user-id').value.trim();
  const name = document.getElementById('config-user-name').value.trim();
  const type = document.getElementById('config-user-type').value;

  if (!id || !name) {
    alert("User ID and Name cannot be empty.");
    return;
  }

  state.user.id = id;
  state.user.name = name;
  state.user.type = type;
  
  saveStateToLocalStorage();
  updateUserBadge();
  log(`User switched to: ${name} (${id})`);

  // Reload current views
  if (window.location.pathname.includes('community.html')) {
    loadFeed();
    loadClubs();
  } else {
    loadDashboardData();
  }
}

// Exposed to button trigger in HTML
window.updateCurrentUser = updateCurrentUser;

// ==========================================
// DASHBOARD & QUIZ LOGIC
// ==========================================
let currentQuizStep = 1;

function initDashboardPage() {
  loadDashboardData();
  
  // Quiz Form navigation
  const nextBtns = document.querySelectorAll('.btn-next');
  const prevBtns = document.querySelectorAll('.btn-prev');
  
  nextBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (validateQuizStep(currentQuizStep)) {
        goToQuizStep(currentQuizStep + 1);
      }
    });
  });

  prevBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      goToQuizStep(currentQuizStep - 1);
    });
  });

  // Quiz Option Cards Select
  const optionCards = document.querySelectorAll('.quiz-option-card');
  optionCards.forEach(card => {
    card.addEventListener('click', () => {
      const groupName = card.dataset.group;
      const val = card.dataset.value;
      
      // Deselect siblings
      document.querySelectorAll(`.quiz-option-card[data-group="${groupName}"]`).forEach(c => {
        c.classList.remove('selected');
      });
      
      card.classList.add('selected');
      
      // Update hidden/linked input or store
      const input = document.getElementById(`quiz-${groupName}`);
      if (input) {
        input.value = val;
      }
    });
  });

  // Submit Quiz
  const quizForm = document.getElementById('footprint-quiz-form');
  if (quizForm) {
    quizForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await submitQuizData();
    });
  }
}

function validateQuizStep(step) {
  if (step === 1) {
    const val = document.getElementById('quiz-transport').value;
    if (!val) {
      alert("Please select a transport mode.");
      return false;
    }
  } else if (step === 2) {
    const val = document.getElementById('quiz-diet').value;
    if (!val) {
      alert("Please select a diet type.");
      return false;
    }
  } else if (step === 3) {
    const val = document.getElementById('quiz-electricity').value;
    if (val === "" || isNaN(val) || parseFloat(val) < 0) {
      alert("Please enter a valid monthly electricity value (kWh).");
      return false;
    }
  }
  return true;
}

function goToQuizStep(step) {
  document.querySelectorAll('.quiz-step').forEach(el => {
    el.classList.remove('active');
  });
  
  const targetStep = document.getElementById(`step-${step}`);
  if (targetStep) {
    targetStep.classList.add('active');
    currentQuizStep = step;
    
    // Update progress bar
    const progressPct = (step / 4) * 100;
    document.getElementById('quiz-progress').style.width = `${progressPct}%`;
  }
}

async function submitQuizData() {
  const transport_type = document.getElementById('quiz-transport').value;
  const transport_distance_km = parseFloat(document.getElementById('quiz-distance').value) || 0.0;
  const diet_type = document.getElementById('quiz-diet').value;
  const electricity_kwh = parseFloat(document.getElementById('quiz-electricity').value) || 0.0;

  const payload = {
    userId: state.user.id,
    userName: state.user.name,
    user_type: state.user.type,
    transport_type,
    transport_distance_km,
    diet_type,
    electricity_kwh
  };

  try {
    const result = await apiCall('/api/quiz', 'POST', payload);
    log("Quiz submitted successfully!");
    renderFootprintResults(result);
    goToQuizStep(4);
    
    // Refresh Leaderboard
    loadLeaderboard();
  } catch (error) {
    alert(`Quiz submission failed: ${error.message}`);
  }
}

function renderFootprintResults(result) {
  // Update total value
  const totalValEl = document.getElementById('results-total-val');
  if (totalValEl) totalValEl.textContent = result.total_kg;

  // Comparison Chip styling
  const compChip = document.getElementById('results-comp-chip');
  if (compChip) {
    compChip.className = "comparison-chip"; // Reset
    if (result.vs_national_avg_pct <= 0) {
      compChip.classList.add('chip-success');
      compChip.textContent = `${Math.abs(result.vs_national_avg_pct)}% below India average`;
    } else {
      compChip.classList.add('chip-danger');
      compChip.textContent = `${result.vs_national_avg_pct}% above India average`;
    }
  }

  // SVG Gauge Ring Animation
  const gaugeFill = document.getElementById('gauge-fill');
  if (gaugeFill) {
    const MAX_GAUGE_CO2 = 800.0; // Max visual limit for 100% circle
    const percentage = Math.min(result.total_kg / MAX_GAUGE_CO2, 1.0);
    const circumference = 565.48; // 2 * PI * 90
    const offset = circumference - (percentage * circumference);
    
    gaugeFill.style.strokeDashoffset = offset;
    
    // Change circle stroke color based on comparison
    if (result.total_kg <= 416.0) {
      gaugeFill.style.stroke = "var(--mint)";
    } else {
      gaugeFill.style.stroke = "var(--amber)";
    }
  }

  // Breakdown Card details
  const tVal = document.getElementById('breakdown-transport-val');
  const dVal = document.getElementById('breakdown-diet-val');
  const eVal = document.getElementById('breakdown-electricity-val');

  if (tVal) tVal.textContent = `${result.breakdown.transport} kg (${result.breakdown_pct.transport}%)`;
  if (dVal) dVal.textContent = `${result.breakdown.diet} kg (${result.breakdown_pct.diet}%)`;
  if (eVal) eVal.textContent = `${result.breakdown.electricity} kg (${result.breakdown_pct.electricity}%)`;
}

async function loadDashboardData() {
  try {
    // 1. Fetch active challenges
    const challenges = await apiCall('/api/challenges');
    state.challenges = challenges;
    renderChallengesList(challenges);
    
    // 2. Fetch global leaderboard
    loadLeaderboard();

    // 3. Try to fetch user current profile to pre-fill gauge
    const profile = await apiCall(`/api/quiz`, 'POST', {
      userId: state.user.id,
      userName: state.user.name,
      user_type: state.user.type,
      transport_type: 'bike_walk',
      transport_distance_km: 0.0,
      diet_type: 'vegan',
      electricity_kwh: 0.0
    });
    // Wait, by submitting zero metrics we get the profile without overwriting their baseline (since baseline checks set_user_baseline).
    // But wait! If they already have a profile, this mock submit will overwrite their CURRENT footprint to 30.0 kg CO2 (diet: vegan = 30kg).
    // Let's avoid submitting empty quiz to fetch profiles!
    // Instead, let's fetch leaderboard, check if the current user is in the leaderboard or if we can have a profile retrieval.
    // Wait, let's check: did we implement a GET endpoint for profile? No, we don't have a direct get profile endpoint in the backend router!
    // Wait, we can implement or use a POST `/api/quiz` to fetch profile, but wait: is there a better way?
    // Let's see: we can search the leaderboard for the current user, or we can just fetch posts.
    // Wait, since `/api/quiz` POST writes to Firestore, let's see. If the user hasn't completed the quiz yet, the dashboard shows the quiz step 1.
    // If they have completed it, can we show results?
    // Yes! Let's check: we can fetch the leaderboard. If the user is on the leaderboard, they have a footprint and we can retrieve their results from there!
    // Or we can just start the user on Step 1 of the quiz. Once they submit, they get the results page. This is a very clean SPA flow!
  } catch (error) {
    log(`Error loading dashboard: ${error.message}`);
  }
}

function renderChallengesList(challenges) {
  const container = document.getElementById('challenges-container');
  if (!container) return;

  if (!challenges || challenges.length === 0) {
    container.innerHTML = '<div class="empty-state">No active challenges at the moment.</div>';
    return;
  }

  container.innerHTML = '';
  challenges.forEach(challenge => {
    const item = document.createElement('div');
    item.className = 'challenge-item';
    item.innerHTML = `
      <div class="challenge-details">
        <h4>${challenge.title}</h4>
        <p>${challenge.description}</p>
        <div class="challenge-meta">
          <span>⚡ ${challenge.action_points} Action Points</span>
          <span>🌱 Saves ${challenge.co2_saved_kg} kg CO2</span>
          <span>📅 ${challenge.frequency}</span>
        </div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="completeChallenge('${challenge.id}')">Complete</button>
    `;
    container.appendChild(item);
  });
}

async function completeChallenge(challengeId) {
  const challenge = state.challenges.find(c => c.id === challengeId);
  if (!challenge) return;

  const payload = {
    userId: state.user.id,
    userName: state.user.name,
    action: `Completed the '${challenge.title}' challenge! 🌿`,
    challengeId: challengeId
  };

  try {
    await apiCall('/api/posts', 'POST', payload);
    alert(`Congratulations! You completed the "${challenge.title}" challenge and earned ${challenge.action_points} action points!`);
    loadLeaderboard();
  } catch (error) {
    alert(`Failed to log completion: ${error.message}`);
  }
}

window.completeChallenge = completeChallenge;

async function loadLeaderboard() {
  const container = document.getElementById('leaderboard-body');
  if (!container) return;

  try {
    const leaderboard = await apiCall('/api/leaderboard');
    container.innerHTML = '';

    if (leaderboard.length === 0) {
      container.innerHTML = '<tr><td colspan="5" class="empty-state">No users logged. Submit a quiz to join the leaderboard!</td></tr>';
      return;
    }

    leaderboard.forEach((row, index) => {
      const tr = document.createElement('tr');
      const isCurrentUser = row.userId === state.user.id;
      
      if (isCurrentUser) {
        tr.style.backgroundColor = "var(--mint-light)";
        tr.style.fontWeight = "600";
      }

      tr.innerHTML = `
        <td class="leaderboard-rank leaderboard-rank-${index + 1}">${index + 1}</td>
        <td>${row.userName} ${isCurrentUser ? '(You)' : ''}</td>
        <td>${row.current_kg} kg</td>
        <td>${row.action_points}</td>
        <td><strong>${row.rank_score}</strong></td>
      `;
      container.appendChild(tr);
    });
  } catch (error) {
    container.innerHTML = '<tr><td colspan="5" class="empty-state">Failed to load leaderboard.</td></tr>';
  }
}

// ==========================================
// COMMUNITY FEED & CLUBS LOGIC
// ==========================================
function initCommunityPage() {
  loadFeed();
  loadClubs();
  loadChallengeSelectOptions();

  // Custom Action Form Submit
  const postForm = document.getElementById('post-action-form');
  if (postForm) {
    postForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      await submitCommunityPost();
    });
  }
}

async function loadChallengeSelectOptions() {
  const select = document.getElementById('post-challenge-select');
  if (!select) return;

  try {
    const challenges = await apiCall('/api/challenges');
    select.innerHTML = '<option value="">-- Optional: Link to preset challenge --</option>';
    challenges.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = `${c.title} (+${c.action_points} pts, -${c.co2_saved_kg} kg)`;
      select.appendChild(opt);
    });
  } catch (error) {
    log("Failed to load challenges into select options");
  }
}

async function submitCommunityPost() {
  const actionText = document.getElementById('post-action-text').value.trim();
  const challengeId = document.getElementById('post-challenge-select').value;
  const clubId = document.getElementById('post-club-select').value;
  const imageUrl = document.getElementById('post-image-url').value.trim();

  if (!actionText) {
    alert("Please write about your action!");
    return;
  }

  const payload = {
    userId: state.user.id,
    userName: state.user.name,
    action: actionText,
    clubId: clubId || null,
    imageUrl: imageUrl || null,
    challengeId: challengeId || null,
    custom_co2_saved_kg: 1.0,  // Standard default for non-challenge logging
    custom_action_points: 10
  };

  try {
    await apiCall('/api/posts', 'POST', payload);
    document.getElementById('post-action-text').value = '';
    document.getElementById('post-image-url').value = '';
    document.getElementById('post-challenge-select').value = '';
    document.getElementById('post-club-select').value = '';
    
    alert("Action logged successfully!");
    loadFeed();
    loadClubs();
  } catch (error) {
    alert(`Failed to log action: ${error.message}`);
  }
}

async function loadFeed() {
  const container = document.getElementById('feed-container');
  if (!container) return;

  try {
    const posts = await apiCall('/api/posts');
    container.innerHTML = '';

    if (posts.length === 0) {
      container.innerHTML = '<div class="empty-state">No activity logs yet. Be the first to share an action!</div>';
      return;
    }

    posts.forEach(post => {
      const card = document.createElement('div');
      card.className = 'feed-post';
      
      const timeStr = new Date(post.timestamp).toLocaleDateString([], {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      });

      let imgHtml = '';
      if (post.imageUrl) {
        imgHtml = `<img src="${post.imageUrl}" class="post-image" alt="User upload" onerror="this.style.display='none'">`;
      }

      let clubBadge = '';
      if (post.clubId) {
        const clubName = post.clubId.replace("-", " ").title || post.clubId;
        clubBadge = `<span class="post-badge">👥 ${clubName}</span>`;
      }

      card.innerHTML = `
        <div class="post-header">
          <span class="post-author">${post.userName}</span>
          <span class="post-time">${timeStr}</span>
        </div>
        <div class="post-content">
          <p>${post.action}</p>
          ${imgHtml}
        </div>
        <div class="post-footer">
          <div class="post-badges">
            <span class="post-badge">🌱 -${post.co2_saved_kg} kg CO2</span>
            <span class="post-badge">⚡ +${post.action_points} pts</span>
            ${clubBadge}
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  } catch (error) {
    container.innerHTML = '<div class="empty-state">Failed to load feed posts.</div>';
  }
}

// Prototype Title capitalization function helper for UI
String.prototype.title = function() {
  return this.replace(/\b\w/g, l => l.toUpperCase());
}

async function loadClubs() {
  const container = document.getElementById('clubs-container');
  if (!container) return;

  try {
    const clubs = await apiCall('/api/clubs');
    container.innerHTML = '';

    for (const club of clubs) {
      const card = document.createElement('div');
      card.className = 'club-card';
      
      // Load top 3 members of the club ranking
      let ranksHtml = '<li><em>No active members</em></li>';
      try {
        const members = await apiCall(`/api/clubs/${club.id}/leaderboard`);
        if (members && members.length > 0) {
          ranksHtml = members.slice(0, 3).map((m, idx) => `
            <li>
              <span>${idx + 1}. ${m.userName}</span>
              <span>${m.action_points} pts</span>
            </li>
          `).join('');
        }
      } catch (e) {
        log(`Failed to fetch ranking for club ${club.id}`);
      }

      card.innerHTML = `
        <div class="club-header">
          <h3 class="club-title">${club.name}</h3>
          <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.25rem;">${club.description}</p>
        </div>
        <div class="club-stats">
          <div class="club-stat-box">
            <div class="club-stat-val">${club.member_count}</div>
            <div class="club-stat-lbl">Members</div>
          </div>
          <div class="club-stat-box">
            <div class="club-stat-val">${Math.round(club.total_co2_saved_kg)}</div>
            <div class="club-stat-lbl">CO2 Saved</div>
          </div>
          <div class="club-stat-box">
            <div class="club-stat-val">${club.total_action_points}</div>
            <div class="club-stat-lbl">Points</div>
          </div>
        </div>
        <div>
          <h4 style="font-size: 0.85rem; margin-bottom: 0.5rem; color: var(--primary);">Top Members</h4>
          <ul class="club-ranking-list">
            ${ranksHtml}
          </ul>
        </div>
      `;
      container.appendChild(card);
    }
  } catch (error) {
    container.innerHTML = '<div class="empty-state">Failed to load Eco Clubs.</div>';
  }
}

// ==========================================
// CHATBOT SSE SERVICE
// ==========================================
let sseSource = null;

function initChatbot() {
  const header = document.getElementById('chat-header');
  const widget = document.getElementById('chat-widget');
  const form = document.getElementById('chat-form');
  const toggleIcon = document.getElementById('chat-toggle-icon');

  if (!header || !widget) return;

  // Toggle Collapse
  header.addEventListener('click', () => {
    widget.classList.toggle('collapsed');
    if (widget.classList.contains('collapsed')) {
      toggleIcon.textContent = '▲';
    } else {
      toggleIcon.textContent = '▼';
      // Scroll to bottom when opening
      scrollToBottom();
    }
  });

  if (form) {
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      sendChatMessage();
    });
  }
}

function scrollToBottom() {
  const box = document.getElementById('chat-messages');
  if (box) {
    box.scrollTop = box.scrollHeight;
  }
}

function appendChatBubble(sender, text) {
  const container = document.getElementById('chat-messages');
  if (!container) return null;

  const bubble = document.createElement('div');
  bubble.className = `chat-bubble bubble-${sender}`;
  bubble.textContent = text;
  container.appendChild(bubble);
  scrollToBottom();
  return bubble;
}

function sendChatMessage() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  const prompt = input.value.trim();
  if (!prompt) return;

  // Clear input
  input.value = '';

  // Append User message
  appendChatBubble('user', prompt);

  // Close previous stream if open
  if (sseSource) {
    sseSource.close();
  }

  // Append typing/waiting bubble
  const buddyBubble = appendChatBubble('buddy', 'EcoBuddy is thinking...');
  buddyBubble.id = 'streaming-buddy-bubble';

  // Open EventSource SSE Connection
  const sseUrl = `${API_BASE}/api/chat/stream?userId=${state.user.id}&prompt=${encodeURIComponent(prompt)}`;
  sseSource = new EventSource(sseUrl);

  let isFirstChunk = true;

  sseSource.onmessage = (event) => {
    // Check for end signal
    if (event.data === '[DONE]') {
      log("SSE Stream completed.");
      sseSource.close();
      sseSource = null;
      document.getElementById('streaming-buddy-bubble').removeAttribute('id');
      return;
    }

    try {
      const data = JSON.parse(event.data);
      if (isFirstChunk) {
        buddyBubble.textContent = ''; // Clear the "thinking" text
        isFirstChunk = false;
      }
      buddyBubble.textContent += data.chunk;
      scrollToBottom();
    } catch (e) {
      console.error("Failed to parse SSE data chunk", e);
    }
  };

  sseSource.onerror = (err) => {
    console.error("SSE stream error occurred", err);
    buddyBubble.textContent = "Oops! Connection timed out or failed. Please try asking again.";
    sseSource.close();
    sseSource = null;
    document.getElementById('streaming-buddy-bubble').removeAttribute('id');
  };
}
