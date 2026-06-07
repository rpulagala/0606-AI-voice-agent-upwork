'use strict';

/* ── Config ──────────────────────────────────────────────────────────────── */
const WS_PROTO      = location.protocol === 'https:' ? 'wss' : 'ws';
const WS_URL        = `${WS_PROTO}://${location.host}/ws/voice`;
const CAPTURE_RATE  = 16000;          // must match Deepgram LiveOptions sample_rate
const CHUNK_SAMPLES = CAPTURE_RATE * 0.1;  // 100 ms = 1600 samples per WebSocket frame

/* ── AudioWorklet source (inlined as blob URL — no separate file needed) ─ */
const WORKLET_SRC = `
class PCMCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this._buf = new Int16Array(${CHUNK_SAMPLES});
    this._len = 0;
  }
  process(inputs) {
    const ch = inputs[0]?.[0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this._buf[this._len++] = Math.max(-32768, Math.min(32767, ch[i] * 32768));
      if (this._len === ${CHUNK_SAMPLES}) {
        this.port.postMessage(this._buf.buffer, [this._buf.buffer]);
        this._buf = new Int16Array(${CHUNK_SAMPLES});
        this._len = 0;
      }
    }
    return true;
  }
}
registerProcessor('pcm-capture', PCMCapture);
`;

/* ── State ───────────────────────────────────────────────────────────────── */
let ws           = null;
let captureCtx   = null;   // 16 kHz context for mic capture
let playbackCtx  = null;   // native-rate context for MP3 playback
let workletNode  = null;
let micStream    = null;
let mp3Chunks    = [];     // accumulates incoming binary frames
let mp3Bytes     = 0;
let activeSource = null;   // currently playing AudioBufferSourceNode

const STATES = {
  IDLE:       'idle',
  CONNECTING: 'connecting',
  LISTENING:  'listening',
  PROCESSING: 'processing',
  SPEAKING:   'speaking',
};
let state = STATES.IDLE;

/* ── UI elements ─────────────────────────────────────────────────────────── */
const btnConnect  = document.getElementById('btn-connect');
const btnDisconn  = document.getElementById('btn-disconnect');
const statusEl    = document.getElementById('status');
const micRing     = document.getElementById('mic-ring');
const transcriptEl = document.getElementById('transcript');

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function setState(s, message) {
  state = s;
  const labels = {
    [STATES.IDLE]:       message || 'Click to connect',
    [STATES.CONNECTING]: 'Connecting...',
    [STATES.LISTENING]:  'Listening...',
    [STATES.PROCESSING]: 'Processing...',
    [STATES.SPEAKING]:   'Speaking...',
  };
  statusEl.textContent = labels[s] ?? s;
  statusEl.className   = `status ${s}`;
  micRing.className    = `mic-ring ${s}`;
}

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const label = document.createElement('span');
  label.className = 'msg-label';
  label.textContent = role === 'user' ? 'You' : 'Agent';
  const body = document.createElement('span');
  body.textContent = text;
  div.appendChild(label);
  div.appendChild(body);
  transcriptEl.appendChild(div);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

/* ── Connect ─────────────────────────────────────────────────────────────── */
async function connect() {
  if (state !== STATES.IDLE) return;
  setState(STATES.CONNECTING);
  btnConnect.disabled = true;

  try {
    // 1. Request microphone — explicit AEC/NS to reduce echo from speakers
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      video: false,
    });

    // 2. Capture AudioContext at 16 kHz — browser resamples mic input automatically
    captureCtx  = new AudioContext({ sampleRate: CAPTURE_RATE });
    playbackCtx = new AudioContext();

    // Resume contexts (required after user gesture in some browsers)
    if (captureCtx.state === 'suspended')  await captureCtx.resume();
    if (playbackCtx.state === 'suspended') await playbackCtx.resume();

    // 3. Load AudioWorklet processor from blob URL
    const blob       = new Blob([WORKLET_SRC], { type: 'application/javascript' });
    const workletUrl = URL.createObjectURL(blob);
    await captureCtx.audioWorklet.addModule(workletUrl);
    URL.revokeObjectURL(workletUrl);

    // 4. Mic source → worklet → WebSocket
    const micSource = captureCtx.createMediaStreamSource(micStream);
    workletNode     = new AudioWorkletNode(captureCtx, 'pcm-capture');
    workletNode.port.onmessage = (e) => {
      // Gate mic only while TTS audio is playing (SPEAKING).
      // PROCESSING has no audio output so no echo risk — user can still barge in.
      if (ws?.readyState === WebSocket.OPEN && state !== STATES.SPEAKING) ws.send(e.data);
    };
    micSource.connect(workletNode);

    // 5. Open WebSocket
    ws = new WebSocket(WS_URL);
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      setState(STATES.LISTENING);
      btnDisconn.style.display = 'inline-block';
    };

    ws.onclose = () => cleanup('Disconnected.');

    ws.onerror = () => cleanup('Connection error.');

    ws.onmessage = async (event) => {
      if (event.data instanceof ArrayBuffer) {
        // MP3 audio chunk from TTS — buffer until response_done
        mp3Chunks.push(event.data);
        mp3Bytes += event.data.byteLength;
        if (state === STATES.LISTENING || state === STATES.PROCESSING) {
          setState(STATES.PROCESSING);
        }
      } else {
        const msg = JSON.parse(event.data);

        if (msg.type === 'transcript') {
          addMessage('user', msg.text);
          setState(STATES.PROCESSING);

        } else if (msg.type === 'speech_start') {
          // Barge-in: user started speaking — stop playback and clear buffer
          if (activeSource) {
            try { activeSource.stop(); } catch (_) {}
            activeSource = null;
          }
          mp3Chunks = [];
          mp3Bytes  = 0;
          setState(STATES.LISTENING);

        } else if (msg.type === 'response_done') {
          await playResponse();
        }
      }
    };

  } catch (err) {
    console.error('Connect error:', err);
    const msg = err.name === 'NotAllowedError'
      ? 'Microphone access denied.'
      : `Error: ${err.message}`;
    cleanup(msg);
  }
}

/* ── Playback ────────────────────────────────────────────────────────────── */
async function playResponse() {
  if (!mp3Chunks.length) {
    setState(STATES.LISTENING);
    return;
  }

  // Concatenate all MP3 chunks into a single ArrayBuffer
  const combined = new Uint8Array(mp3Bytes);
  let offset = 0;
  for (const buf of mp3Chunks) {
    combined.set(new Uint8Array(buf), offset);
    offset += buf.byteLength;
  }
  mp3Chunks = [];
  mp3Bytes  = 0;

  setState(STATES.SPEAKING);

  try {
    const decoded = await playbackCtx.decodeAudioData(combined.buffer);
    activeSource  = playbackCtx.createBufferSource();
    activeSource.buffer = decoded;
    activeSource.connect(playbackCtx.destination);
    activeSource.onended = () => {
      activeSource = null;
      setState(STATES.LISTENING);
    };
    activeSource.start();
  } catch (err) {
    console.error('MP3 decode error:', err);
    setState(STATES.LISTENING);
  }
}

/* ── Disconnect ──────────────────────────────────────────────────────────── */
function disconnect() {
  cleanup('Disconnected.');
}

function cleanup(message) {
  if (ws)           { try { ws.close();            } catch (_) {} ws = null; }
  if (workletNode)  { try { workletNode.disconnect(); } catch (_) {} workletNode = null; }
  if (captureCtx)   { captureCtx.close();  captureCtx  = null; }
  if (playbackCtx)  { playbackCtx.close(); playbackCtx = null; }
  if (micStream)    { micStream.getTracks().forEach(t => t.stop()); micStream = null; }
  if (activeSource) { try { activeSource.stop(); } catch (_) {} activeSource = null; }
  mp3Chunks = [];
  mp3Bytes  = 0;

  setState(STATES.IDLE, message);
  btnConnect.disabled = false;
  btnDisconn.style.display = 'none';
}

/* ── Button wiring ───────────────────────────────────────────────────────── */
btnConnect.onclick = connect;
btnDisconn.onclick = disconnect;
