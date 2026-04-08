// PocketPD Simulator — Browser Client
// Connects to /ws for OLED display streaming and /ws/status for state updates

// --- OLED Display WebSocket (binary framebuf data) ---

const canvas = document.getElementById('oled-canvas');
const ctx = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;

// Display dimensions (source)
const OLED_W = 128;
const OLED_H = 64;
// Canvas is 3x scaled
const SCALE = canvas.width / OLED_W;

let displayWs = null;

function connectDisplayWs() {
    const url = `ws://${location.host}/ws`;
    displayWs = new WebSocket(url);
    displayWs.binaryType = 'arraybuffer';

    displayWs.onopen = () => console.log('Display WS connected');
    displayWs.onclose = () => setTimeout(connectDisplayWs, 2000);
    displayWs.onerror = () => {};

    displayWs.onmessage = (event) => {
        const data = new Uint8Array(event.data);
        if (data.length < 8) return;

        const msgType = data[0];
        // 0x01 = full frame, 0x03 = init
        if (msgType === 0x01) {
            renderFrame(data);
        }
    };
}

function renderFrame(data) {
    // Header: 8 bytes, then RGBA pixel data
    const header = data.slice(0, 8);
    const width = (header[2] << 8) | header[3];
    const height = (header[4] << 8) | header[5];
    const pixels = data.slice(8);

    if (pixels.length < width * height * 4) return;

    const imageData = ctx.createImageData(width, height);
    imageData.data.set(pixels);

    // Draw at 1:1 then let CSS/canvas scale handle the rest
    // Use a temp canvas for crisp scaling
    const tmp = document.createElement('canvas');
    tmp.width = width;
    tmp.height = height;
    tmp.getContext('2d').putImageData(imageData, 0, 0);

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(tmp, 0, 0, canvas.width, canvas.height);
}

// --- Status WebSocket (JSON) ---

let statusWs = null;

function connectStatusWs() {
    const url = `ws://${location.host}/ws-status`;
    statusWs = new WebSocket(url);

    statusWs.onopen = () => {
        document.getElementById('conn-indicator').className = 'status-indicator connected';
        document.getElementById('conn-text').textContent = 'Connected';
    };
    statusWs.onclose = () => {
        document.getElementById('conn-indicator').className = 'status-indicator disconnected';
        document.getElementById('conn-text').textContent = 'Disconnected — reconnecting...';
        setTimeout(connectStatusWs, 2000);
    };
    statusWs.onerror = () => {};

    statusWs.onmessage = (event) => {
        try {
            const state = JSON.parse(event.data);
            updateStatus(state);
        } catch (e) {}
    };
}

// --- State Machine Diagram (Mermaid) ---

// Map state index + display_energy to Mermaid node name
const STATE_NAMES = {
    0: 'BOOT',
    1: 'OBTAIN',
    2: 'CAPDISPLAY',
    3: 'NORMAL_PPS',
    4: 'NORMAL_PDO',
    5: 'MENU',
};
const ENERGY_NAMES = { 3: 'ENERGY_PPS', 4: 'ENERGY_PDO' };

let lastActiveNode = null;

function findMermaidNode(name) {
    // Mermaid generates IDs like "mermaid-{ts}-state-{NAME}-{n}"
    const svg = document.querySelector('.state-panel svg');
    if (!svg) return null;
    const nodes = svg.querySelectorAll('g[id*="-state-' + name + '-"]');
    return nodes.length ? nodes[0] : null;
}

function updateStateDiagram(stateIdx, displayEnergy) {
    let name = STATE_NAMES[stateIdx] || '';
    if (displayEnergy && ENERGY_NAMES[stateIdx]) {
        name = ENERGY_NAMES[stateIdx];
    }
    if (!name) return;

    // Clear previous highlight
    if (lastActiveNode) {
        lastActiveNode.classList.remove('sm-active');
    }

    const node = findMermaidNode(name);
    if (node) {
        node.classList.add('sm-active');
        lastActiveNode = node;
    }
}

function updateStatus(s) {
    // State machine diagram
    updateStateDiagram(s.state, s.display_energy);

    // Voltage / Current / Power
    document.getElementById('val-voltage').textContent = (s.voltage_mv / 1000).toFixed(2);
    document.getElementById('val-current').textContent = (s.current_ma / 1000).toFixed(3);
    document.getElementById('val-power').textContent = (s.power_mw / 1000).toFixed(2);

    // Output badge
    const outBadge = document.getElementById('badge-output');
    outBadge.textContent = s.output_on ? 'ON' : 'OFF';
    outBadge.className = 'badge ' + (s.output_on ? 'badge-on' : 'badge-off');

    // CV/CC badge
    const modeBadge = document.getElementById('badge-mode');
    modeBadge.textContent = s.cv_mode ? 'CV' : 'CC';
    modeBadge.className = 'badge ' + (s.cv_mode ? 'badge-cv' : 'badge-cc');

    // PPS badge
    const ppsBadge = document.getElementById('badge-pps');
    ppsBadge.style.display = s.has_pps ? '' : 'none';

    // Update input fields (only if not focused)
    const vInput = document.getElementById('input-voltage');
    if (document.activeElement !== vInput) vInput.value = s.target_voltage_mv;
    const iInput = document.getElementById('input-current');
    if (document.activeElement !== iInput) iInput.value = s.target_current_ma;

    // Energy
    const h = Math.floor(s.elapsed_s / 3600);
    const m = Math.floor((s.elapsed_s % 3600) / 60);
    const sec = Math.floor(s.elapsed_s % 60);
    document.getElementById('val-time').textContent =
        `${h}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
    document.getElementById('val-wh').textContent = s.wh.toFixed(3) + ' Wh';
    document.getElementById('val-ah').textContent = s.ah.toFixed(4) + ' Ah';

    // PDO list
    const pdoEl = document.getElementById('pdo-list');
    if (pdoEl.children.length === 0 && (s.fixed_pdos.length || s.pps_pdos.length)) {
        let html = '<h2>Source Profiles</h2>';
        for (const p of s.fixed_pdos) {
            html += `<div class="pdo-item">${(p.voltage_mv/1000).toFixed(1)}V ${(p.max_current_ma/1000).toFixed(1)}A</div>`;
        }
        for (const p of s.pps_pdos) {
            html += `<div class="pdo-item pps">PPS ${(p.min_voltage_mv/1000).toFixed(1)}-${(p.max_voltage_mv/1000).toFixed(1)}V ${(p.max_current_ma/1000).toFixed(1)}A</div>`;
        }
        pdoEl.innerHTML = html;
    }
}

// --- REST API helpers ---

async function apiPost(path, body) {
    try {
        await fetch(path, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
        });
    } catch (e) {
        console.error('API error:', e);
    }
}

function adjustVoltage(delta) {
    const input = document.getElementById('input-voltage');
    input.value = Math.max(0, parseInt(input.value) + delta);
    setVoltage();
}

function adjustCurrent(delta) {
    const input = document.getElementById('input-current');
    input.value = Math.max(0, parseInt(input.value) + delta);
    setCurrent();
}

function setVoltage() {
    const mv = parseInt(document.getElementById('input-voltage').value) || 5000;
    apiPost('/api/voltage', {mv: mv});
}

function setCurrent() {
    const ma = parseInt(document.getElementById('input-current').value) || 3000;
    apiPost('/api/current', {ma: ma});
}

// --- Initialize ---

connectDisplayWs();
connectStatusWs();
