const canvas = document.querySelector('#map');
const context = canvas.getContext('2d');
const controls = document.querySelector('#controls');
const zoomIn = document.querySelector('#zoomIn');
const zoomOut = document.querySelector('#zoomOut');
const point = document.querySelector('#point');
const mapError = document.querySelector('#map-error');
const MIN_ZOOM = 1;
const MAX_ZOOM = 128;
const parentMessage = (type, values = {}) => {
  window.parent.postMessage({isStreamlitMessage: true, type, ...values}, '*');
};

let boundaryPath = null;
let latitude = 30.8;
let longitude = 75.7;
let centerLat = 0;
let centerLon = 0;
let height = 246;
let zoom = MIN_ZOOM;
let fixed = false;
let trend = null;
let projection = null;
let latestProps = null;
const pendingPoints = [];
const clip = (value, limit) => Math.min(Math.max(value, -limit), limit);
const wrapLongitude = value => Math.abs(value) <= 180 ? value : ((value % 360 + 540) % 360) - 180;
const coordinate = (value, labels) => `${Math.abs(value).toFixed(4)}° ${labels[Number(value < 0)]}`;
const labelCoordinates = () => `${coordinate(latitude, ['N', 'S'])}, ${coordinate(longitude, ['E', 'W'])}`;

function traceBoundaries(rings) {
  const path = new Path2D();
  for (const ring of rings) {
    const [first, ...rest] = ring;
    if (!first) continue;
    path.moveTo(...first);
    for (const vertex of rest) path.lineTo(...vertex);
    path.closePath();
  }
  return path;
}

function renderLand(scale, midpointX, midpointY) {
  if (!boundaryPath) return;
  const shifts = zoom === MIN_ZOOM ? [0] : [-360, 0, 360];
  for (const shift of shifts) {
    context.save();
    context.translate(midpointX - (centerLon - shift) * scale, midpointY + centerLat * scale);
    context.scale(scale, -scale);
    context.fillStyle = '#E4E7E5';
    context.strokeStyle = '#A8AEB1';
    context.lineWidth = .7 / scale;
    context.fill(boundaryPath);
    context.stroke(boundaryPath);
    context.restore();
  }
}

function renderTrend(x, y, scale) {
  if (!fixed || trend === null) return;
  const reach = 1.35 / Math.max(Math.cos(latitude * Math.PI / 180), .2);
  const tone = trend < 0 ? '#A4472A' : trend > 0 ? '#3D7FC4' : '#5F656C';
  const west = x(longitude - reach);
  const north = y(latitude + 1.35);
  context.save();
  context.globalAlpha = Math.min(.75, .28 + Math.abs(trend) / 2);
  context.fillStyle = tone;
  context.fillRect(west, north, reach * 2 * scale, 2.7 * scale);
  context.globalAlpha = 1;
  context.strokeStyle = tone;
  context.lineWidth = 1;
  context.strokeRect(west, north, reach * 2 * scale, 2.7 * scale);
  context.restore();
}

function draw() {
  const width = canvas.clientWidth;
  if (!width) return;
  const deviceScale = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * deviceScale);
  canvas.height = Math.round(height * deviceScale);
  context.setTransform(deviceScale, 0, 0, deviceScale, 0, 0);
  const scale = Math.min(width / 360, height / 180) * zoom;
  const midpointX = width / 2;
  const midpointY = height / 2;
  const x = lon => wrapLongitude(lon - centerLon) * scale + midpointX;
  const y = lat => (centerLat - lat) * scale + midpointY;
  projection = {scale, midpointX, midpointY};
  renderLand(scale, midpointX, midpointY);
  renderTrend(x, y, scale);
  context.beginPath();
  context.arc(x(longitude), y(latitude), 5, 0, 2 * Math.PI);
  context.fillStyle = '#24272B';
  context.strokeStyle = '#FFFFFF';
  context.lineWidth = 2;
  context.fill();
  context.stroke();

  const location = labelCoordinates();
  if (point.textContent !== location) {
    point.textContent = location;
    if (fixed) canvas.setAttribute('aria-label', `Field map at ${location}`);
  }
}

function selectPoint(lat, lon) {
  const nextLat = Number(clip(lat, 90).toFixed(5));
  const nextLon = Number(wrapLongitude(lon).toFixed(5));
  if (nextLat === latitude && nextLon === longitude) return;
  latitude = nextLat;
  longitude = nextLon;
  const {scale, midpointX, midpointY} = projection;
  if (zoom > MIN_ZOOM && (
    Math.abs(wrapLongitude(longitude - centerLon) * scale) > midpointX - 14
    || Math.abs((latitude - centerLat) * scale) > midpointY - 14
  )) centerOnPin();
  draw();
  pendingPoints.push([latitude, longitude]);
  parentMessage('streamlit:setComponentValue', {value: {lat: latitude, lon: longitude}, dataType: 'json'});
}

function centerOnPin() {
  [centerLat, centerLon] = zoom === MIN_ZOOM ? [0, 0] : [latitude, longitude];
}

function updateZoom(nextZoom) {
  zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, nextZoom));
  zoomIn.disabled = zoom === MAX_ZOOM;
  zoomOut.disabled = zoom === MIN_ZOOM;
  centerOnPin();
  draw();
}

canvas.addEventListener('click', event => {
  if (fixed || !projection || !boundaryPath) return;
  const rect = canvas.getBoundingClientRect();
  const {scale, midpointX, midpointY} = projection;
  const rawLat = centerLat - (event.clientY - rect.top - midpointY) / scale;
  const rawLon = centerLon + (event.clientX - rect.left - midpointX) / scale;
  if (Math.abs(rawLat) > 90 || (zoom === MIN_ZOOM && Math.abs(rawLon) > 180)) return;
  selectPoint(rawLat, rawLon);
});

canvas.addEventListener('keydown', event => {
  if (fixed || !projection) return;
  const step = 1 / zoom;
  const moves = {ArrowUp: [step, 0], ArrowDown: [-step, 0], ArrowLeft: [0, -step], ArrowRight: [0, step]};
  if (Object.hasOwn(moves, event.key)) {
    event.preventDefault();
    const [north, east] = moves[event.key];
    selectPoint(latitude + north, longitude + east);
  } else if (event.key === '+' || event.key === '=' || event.key === '-' || event.key === 'Home') {
    event.preventDefault();
    updateZoom(event.key === 'Home' ? MIN_ZOOM : zoom * (event.key === '-' ? .5 : 2));
  }
});

zoomIn.addEventListener('click', () => updateZoom(zoom * 2));
zoomOut.addEventListener('click', () => updateZoom(zoom / 2));
window.addEventListener('message', event => {
  if (event.source !== window.parent || event.data?.type !== 'streamlit:render') return;
  const args = event.data.args;
  fixed = args.fixed;
  const newCoordinates = [Number(args.lat), Number(args.lon)];
  if (!latestProps || latestProps.some((value, index) => value !== newCoordinates[index])) {
    latestProps = newCoordinates;
    // A server redraw may still carry the previous pin while it processes the next movement.
    const ack = pendingPoints.findIndex(([lat, lon]) => lat === newCoordinates[0] && lon === newCoordinates[1]);
    if (ack !== -1) {
      pendingPoints.splice(0, ack + 1);
    } else if (latitude !== newCoordinates[0] || longitude !== newCoordinates[1]) {
      pendingPoints.length = 0;
      [latitude, longitude] = newCoordinates;
      centerOnPin();
    }
  }
  trend = Number.isFinite(args.trend) ? args.trend : null;
  height = args.height;
  controls.hidden = fixed;
  canvas.setAttribute('role', fixed ? 'img' : 'group');
  if (fixed) {
    canvas.removeAttribute('tabindex');
    canvas.removeAttribute('aria-describedby');
    canvas.setAttribute('aria-label', `Field map at ${labelCoordinates()}`);
    zoom = 38;
    centerOnPin();
  }
  zoomIn.disabled = zoom === MAX_ZOOM;
  zoomOut.disabled = zoom === MIN_ZOOM;
  canvas.style.height = `${height}px`;
  parentMessage('streamlit:setFrameHeight', {height: height + 2});
  draw();
});

new ResizeObserver(draw).observe(canvas);
fetch('./boundaries.json').then(response => {
  if (!response.ok) throw new Error('Map boundary file is unavailable');
  return response.json();
}).then(rings => {
  boundaryPath = traceBoundaries(rings);
  draw();
}).catch(() => {
  mapError.hidden = false;
  draw();
});
parentMessage('streamlit:componentReady', {apiVersion: 1});
