const canvas = document.querySelector('#map');
const context = canvas.getContext('2d');
const controls = document.querySelector('#controls');
const parentMessage = (type, values = {}) => window.parent.postMessage({isStreamlitMessage: true, type, ...values}, '*');
let boundaries = [];
let latitude = 30.8;
let longitude = 75.7;
let height = 232;
let zoom = 1;
let fixed = false;
let trend = null;
let coordinateMap = null;
let lastSelection = null;
const clip = (value, limit) => Math.min(Math.max(value, -limit), limit);

function draw() {
  const width = canvas.clientWidth;
  if (!width) return;
  const deviceScale = window.devicePixelRatio || 1;
  canvas.width = width * deviceScale;
  canvas.height = height * deviceScale;
  context.setTransform(deviceScale, 0, 0, deviceScale, 0, 0);
  const lonScale = width * zoom / 360;
  const latScale = height * zoom / 180;
  const centerLon = zoom === 1 ? 0 : longitude;
  const centerLat = zoom === 1 ? 0 : latitude;
  const x = lon => (lon - centerLon) * lonScale + width / 2;
  const y = lat => (centerLat - lat) * latScale + height / 2;
  coordinateMap = {width, lonScale, latScale, centerLon, centerLat, x, y};
  context.lineWidth = 1;
  context.fillStyle = '#e8e5de';
  context.strokeStyle = '#a9afb3';
  for (const ring of boundaries) {
    context.beginPath();
    ring.forEach(([lon, lat], index) => index === 0 ? context.moveTo(x(lon), y(lat)) : context.lineTo(x(lon), y(lat)));
    context.closePath();
    context.fill();
    context.stroke();
  }
  if (fixed && trend !== null) {
    const reach = 1.35 / Math.max(Math.cos(latitude * Math.PI / 180), .2);
    context.globalAlpha = Math.min(.78, .22 + Math.abs(trend) / 2);
    context.fillStyle = trend < 0 ? '#A4472A' : '#3D7FC4';
    context.fillRect(x(longitude - reach), y(latitude + 1.35), reach * 2 * lonScale, 2.7 * latScale);
    context.globalAlpha = 1;
  }
  context.beginPath();
  context.arc(x(longitude), y(latitude), 4, 0, 2 * Math.PI);
  context.fillStyle = '#24272B';
  context.strokeStyle = '#FFFFFF';
  context.lineWidth = 1.5;
  context.fill();
  context.stroke();
}

function select(lat, lon) {
  latitude = Number(clip(lat, 90).toFixed(5));
  longitude = Number(clip(lon, 180).toFixed(5));
  lastSelection = [latitude, longitude];
  draw();
  parentMessage('streamlit:setComponentValue', {value: {lat: latitude, lon: longitude}, dataType: 'json'});
}

canvas.addEventListener('click', event => {
  if (fixed || !coordinateMap) return;
  const rect = canvas.getBoundingClientRect();
  const {width, lonScale, latScale, centerLon, centerLat} = coordinateMap;
  select(centerLat - (event.clientY - rect.top - height / 2) / latScale,
         centerLon + (event.clientX - rect.left - width / 2) / lonScale);
});

canvas.addEventListener('keydown', event => {
  if (fixed) return;
  const shift = 1 / zoom;
  const offsets = {ArrowUp: [shift, 0], ArrowDown: [-shift, 0], ArrowLeft: [0, -shift], ArrowRight: [0, shift]};
  if (event.key in offsets) {
    event.preventDefault();
    const [north, east] = offsets[event.key];
    select(latitude + north, longitude + east);
  }
});

document.querySelector('#zoomIn').onclick = () => { zoom = Math.min(128, zoom * 2); draw(); };
document.querySelector('#zoomOut').onclick = () => { zoom = Math.max(1, zoom / 2); draw(); };
window.addEventListener('message', event => {
  if (event.source !== window.parent || event.data.type !== 'streamlit:render') return;
  const args = event.data.args;
  fixed = args.fixed;
  [latitude, longitude] = !fixed && lastSelection ? lastSelection : [args.lat, args.lon];
  trend = args.trend;
  height = args.height;
  zoom = fixed ? 38 : zoom;
  controls.hidden = fixed;
  canvas.style.height = height + 'px';
  parentMessage('streamlit:setFrameHeight', {height});
  draw();
});
new ResizeObserver(draw).observe(canvas);
fetch('./boundaries.json').then(response => response.json()).then(rings => { boundaries = rings; draw(); });
parentMessage('streamlit:componentReady', {apiVersion: 1});
