// MediaPipe Hands gesture tracker
// window.THREE must be set before calling init()

const CFG = {
  pinchDist:      0.07,   // thumb-index dist threshold
  pinchOpenMs:    600,    // max ms pinch→open for explode
  debounceFrames: 3,      // frames same gesture before reporting
  posAlpha:       0.25,   // EMA for position (lower = smoother)
  velAlpha:       0.18,   // EMA for velocity
};

let camera3D     = null;
let lastGesture  = 'none';
let pendingGesture = 'none';
let pendingCount   = 0;

let pinchStartTime = null;  // tracks when pinch began

// Smoothed position and velocity
let smoothPos = { x: 0, y: 0, z: 0 };
let smoothVel = { x: 0, y: 0, z: 0 };
let prevSmoothedPos = null;
let prevTime  = performance.now();

/**
 * @param {HTMLVideoElement} videoEl
 * @param {THREE.PerspectiveCamera} camera
 * @param {Function} onGesture — ({gesture, worldPos, velocity}) each frame
 */
export async function init(videoEl, camera, onGesture) {
  camera3D = camera;

  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/hands/hands.js');
  await _loadScript('https://cdn.jsdelivr.net/npm/@mediapipe/camera_utils/camera_utils.js');

  const hands = new window.Hands({
    locateFile: (f) => `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${f}`,
  });

  hands.setOptions({
    maxNumHands:            1,
    modelComplexity:        1,
    minDetectionConfidence: 0.65,
    minTrackingConfidence:  0.55,
  });

  hands.onResults((results) => {
    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
      _commitGesture('none', null, null, onGesture);
      return;
    }

    const lm  = results.multiHandLandmarks[0];
    const raw = _landmarkToWorld(lm[9]);

    const now = performance.now();
    const dt  = Math.max((now - prevTime) / 1000, 0.001);
    prevTime  = now;

    // EMA position smoothing
    if (prevSmoothedPos === null) {
      smoothPos = { ...raw };
    } else {
      smoothPos.x += CFG.posAlpha * (raw.x - smoothPos.x);
      smoothPos.y += CFG.posAlpha * (raw.y - smoothPos.y);
      smoothPos.z += CFG.posAlpha * (raw.z - smoothPos.z);
    }

    // Raw velocity then EMA smooth
    const rawVel = prevSmoothedPos
      ? {
          x: (smoothPos.x - prevSmoothedPos.x) / dt,
          y: (smoothPos.y - prevSmoothedPos.y) / dt,
          z: (smoothPos.z - prevSmoothedPos.z) / dt,
        }
      : { x: 0, y: 0, z: 0 };

    smoothVel.x += CFG.velAlpha * (rawVel.x - smoothVel.x);
    smoothVel.y += CFG.velAlpha * (rawVel.y - smoothVel.y);
    smoothVel.z += CFG.velAlpha * (rawVel.z - smoothVel.z);

    prevSmoothedPos = { ...smoothPos };

    const rawGesture = _classify(lm, now);
    _commitGesture(rawGesture, { ...smoothPos }, { ...smoothVel }, onGesture);
  });

  const mpCamera = new window.Camera(videoEl, {
    onFrame: async () => { await hands.send({ image: videoEl }); },
    width: 640,
    height: 480,
  });
  mpCamera.start();
}

// Instantaneous gestures bypass debounce — fire on first frame
const INSTANT_GESTURES = new Set(['explode', 'pinch']);

function _commitGesture(gesture, pos, vel, onGesture) {
  if (INSTANT_GESTURES.has(gesture)) {
    lastGesture    = gesture;
    pendingGesture = gesture;
    pendingCount   = CFG.debounceFrames;
    onGesture({ gesture, worldPos: pos, velocity: vel });
    return;
  }

  if (gesture === pendingGesture) {
    pendingCount++;
  } else {
    pendingGesture = gesture;
    pendingCount   = 1;
  }

  if (pendingCount >= CFG.debounceFrames || gesture === 'none') {
    if (gesture !== lastGesture || gesture !== 'none') {
      lastGesture = gesture;
      onGesture({ gesture, worldPos: pos, velocity: vel });
    }
  }
}

function _loadScript(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) { resolve(); return; }
    const s = document.createElement('script');
    s.src     = src;
    s.onload  = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

function _dist(a, b) {
  return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2);
}

function _fingerExtended(tip, pip) {
  // tip.y < pip.y — tip above PIP in image space (y goes down). Relaxed threshold.
  return tip.y < pip.y + 0.01;
}

function _classify(lm, now) {
  const thumbTip  = lm[4];
  const indexTip  = lm[8];
  const middleTip = lm[12];
  const ringTip   = lm[16];
  const pinkyTip  = lm[20];

  const isPinch = _dist(thumbTip, indexTip) < CFG.pinchDist;

  const indexExt  = _fingerExtended(indexTip,  lm[6]);
  const middleExt = _fingerExtended(middleTip, lm[10]);
  const ringExt   = _fingerExtended(ringTip,   lm[14]);
  const pinkyExt  = _fingerExtended(pinkyTip,  lm[18]);
  const extCount  = [indexExt, middleExt, ringExt, pinkyExt].filter(Boolean).length;

  // Pinch held
  if (isPinch) {
    if (pinchStartTime === null) pinchStartTime = now;
    return 'pinch';
  }

  // Explode: pinch released → hand open (≥2 fingers free) within window
  if (pinchStartTime !== null) {
    const held = now - pinchStartTime;
    pinchStartTime = null;
    if (extCount >= 2 && held < CFG.pinchOpenMs) return 'explode';
  }

  // Fist: no fingers extended
  if (extCount === 0) return 'attract';

  // Repel: only index extended
  if (indexExt && !middleExt && !ringExt && !pinkyExt) return 'repel';

  // Rotate: peace sign — index + middle extended, ring + pinky curled
  if (indexExt && middleExt && !ringExt && !pinkyExt) return 'rotate';

  // Open hand — no specific gesture, neutral
  return 'none';
}

function _landmarkToWorld(lm) {
  const THREE = window.THREE;
  const ndcX  =  (lm.x * 2) - 1;
  const ndcY  = -(lm.y * 2) + 1;

  const v   = new THREE.Vector3(ndcX, ndcY, 0.5);
  v.unproject(camera3D);
  const dir = v.sub(camera3D.position).normalize();
  const t   = -camera3D.position.z / dir.z;
  const wp  = camera3D.position.clone().add(dir.multiplyScalar(t));

  return { x: wp.x, y: wp.y, z: wp.z };
}
