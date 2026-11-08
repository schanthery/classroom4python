// Serveur de synchronisation Yjs de classroom4python
//  - salles en mémoire (comme avant) ;
//  - GET  /_rooms        : liste des salles (nom, connectés, verrouillée ou non) ;
//  - POST /_admin/lock   : verrouiller / déverrouiller une salle (mot de passe administrateur) ;
//  - POST /_room/create et /_room/settings : droits du créateur, persistés avec un secret local ;
//  - une salle verrouillée est en LECTURE SEULE : le serveur refuse toute modification venant des clients,
//    et elle est sauvegardée sur disque (elle survit au redémarrage du serveur).
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const WebSocket = require('ws');
const Y = require('yjs');
const decoding = require('lib0/decoding');
const { setupWSConnection, docs, getYDoc } = require('y-websocket/bin/utils');

const PORT = process.env.PORT || 1234;
const HOST = process.env.HOST || '127.0.0.1';
const DATA_DIR = process.env.PT_DATA_DIR || path.join(__dirname, 'data');
const ADMIN_PW = process.env.PT_ADMIN_PASSWORD || '';
const ROOM_STRICT = /^[A-Za-z0-9_-]{1,64}$/;      // noms de salles qu'on peut verrouiller (sert aussi de nom de fichier)
const ROOM_CREATE = /^salle-[a-z0-9]{6}$/;

fs.mkdirSync(DATA_DIR, { recursive: true });
const LOCKS_FILE = path.join(DATA_DIR, 'locked-rooms.json');
const ROOM_SETTINGS_FILE = path.join(DATA_DIR, 'room-settings.json');
const stateFile = name => path.join(DATA_DIR, name + '.ydoc');

function atomicWrite(file, data) {
  const tmp = file + '.tmp';
  fs.writeFileSync(tmp, data);
  fs.renameSync(tmp, file);
}

let locked = new Set();
try { locked = new Set(JSON.parse(fs.readFileSync(LOCKS_FILE, 'utf8')).filter(n => ROOM_STRICT.test(n))); } catch (e) { /* aucun verrou enregistré */ }
const saveLocks = () => atomicWrite(LOCKS_FILE, JSON.stringify(Array.from(locked)));

let roomSettings = {};
try {
  const saved = JSON.parse(fs.readFileSync(ROOM_SETTINGS_FILE, 'utf8'));
  if (saved && typeof saved === 'object' && !Array.isArray(saved)) {
    roomSettings = Object.fromEntries(Object.entries(saved).filter(([name, value]) =>
      ROOM_STRICT.test(name) && value && typeof value.ownerName === 'string' &&
      /^[a-f0-9]{64}$/.test(value.ownerKeyHash) &&
      typeof value.ownerLocked === 'boolean' && typeof value.cursorLabels === 'boolean'));
  }
} catch (e) {
  if (e.code !== 'ENOENT') console.error('Lecture impossible des réglages de salles :', e.message);
}
const saveRoomSettings = () => atomicWrite(ROOM_SETTINGS_FILE, JSON.stringify(roomSettings));

function isRoomOwner(name, key) {
  const settings = roomSettings[name];
  if (!settings || typeof key !== 'string' || !/^[a-f0-9]{64}$/.test(key)) return false;
  const supplied = crypto.createHash('sha256').update(key).digest();
  const stored = Buffer.from(settings.ownerKeyHash, 'hex');
  return crypto.timingSafeEqual(supplied, stored);
}

function syncRoomSettings(name, doc) {
  const settings = roomSettings[name];
  if (!settings) return;
  const meta = doc.getMap('meta');
  if (meta.get('ownerName') === settings.ownerName &&
      meta.get('ownerLocked') === settings.ownerLocked &&
      meta.get('cursorLabels') === settings.cursorLabels) return;
  doc.transact(() => {
    meta.set('ownerName', settings.ownerName);
    meta.set('ownerLocked', settings.ownerLocked);
    meta.set('cursorLabels', settings.cursorLabels);
  }, 'server');
}

// Ouvre (ou crée) une salle ; une salle verrouillée est rechargée depuis le disque à sa première ouverture
function openRoom(name) {
  const known = docs.has(name);
  const doc = getYDoc(name);
  if (!known && locked.has(name)) {
    try { Y.applyUpdate(doc, fs.readFileSync(stateFile(name)), 'server'); }
    catch (e) { console.error('Lecture impossible de la salle verrouillée "' + name + '" :', e.message); }
  }
  syncRoomSettings(name, doc);
  return doc;
}

function lockRoom(name) {
  const doc = openRoom(name);
  doc.transact(() => doc.getMap('meta').set('locked', true), 'server');   // les clients passent en lecture seule
  locked.add(name);
  saveLocks();
  atomicWrite(stateFile(name), Buffer.from(Y.encodeStateAsUpdate(doc)));
}

function unlockRoom(name) {
  const doc = openRoom(name);                                              // recharge depuis le disque si besoin
  doc.transact(() => doc.getMap('meta').delete('locked'), 'server');
  locked.delete(name);
  saveLocks();
  try { fs.unlinkSync(stateFile(name)); } catch (e) { /* déjà absent */ }
}

// Un message « sync » de type 1 (étape 2) ou 2 (mise à jour) envoyé par un client modifie le document
function isDocWrite(data) {
  try {
    const dec = decoding.createDecoder(new Uint8Array(data));
    if (decoding.readVarUint(dec) !== 0) return false;      // 0 = message de synchronisation (1 = présence : autorisée)
    const t = decoding.readVarUint(dec);
    return t === 1 || t === 2;
  } catch (e) {
    return true;                                            // message illisible : refusé dans une salle verrouillée
  }
}

function json(res, code, obj) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(obj));
}

function readBody(req, max, cb) {
  let body = '';
  req.setEncoding('utf8');
  req.on('data', c => { body += c; if (body.length > max) { req.destroy(); } });
  req.on('end', () => cb(body));
}

function handleCreateRoom(req, res) {
  readBody(req, 4096, body => {
    let j;
    try { j = JSON.parse(body); } catch (e) { return json(res, 400, { error: 'Requête invalide' }); }
    const name = String(j.room || '');
    const ownerName = String(j.ownerName || '').trim().slice(0, 20);
    const ownerKey = String(j.ownerKey || '');
    if (!ROOM_CREATE.test(name)) return json(res, 400, { error: 'Nom de salle invalide' });
    if (!ownerName || !/^[a-f0-9]{64}$/.test(ownerKey)) return json(res, 400, { error: 'Identité du créateur invalide' });
    if (roomSettings[name] || docs.has(name) || locked.has(name)) return json(res, 409, { error: 'Cette salle existe déjà' });
    roomSettings[name] = {
      ownerName,
      ownerKeyHash: crypto.createHash('sha256').update(ownerKey).digest('hex'),
      ownerLocked: false,
      cursorLabels: true
    };
    try {
      saveRoomSettings();
      openRoom(name);
    } catch (e) {
      delete roomSettings[name];
      try { saveRoomSettings(); } catch (saveError) { console.error(saveError); }
      console.error(e);
      return json(res, 500, { error: 'Création de la salle impossible' });
    }
    json(res, 201, { ok: true });
  });
}

function handleRoomState(req, res) {
  const url = new URL(req.url, 'http://localhost');
  const name = url.searchParams.get('room') || '';
  if (!ROOM_STRICT.test(name)) return json(res, 400, { error: 'Nom de salle invalide' });
  const settings = roomSettings[name];
  if (!settings) return json(res, 404, { error: 'Salle inconnue' });
  const authorization = req.headers.authorization || '';
  const ownerKey = authorization.startsWith('Bearer ') ? authorization.slice(7) : '';
  json(res, 200, {
    ownerName: settings.ownerName,
    ownerLocked: settings.ownerLocked,
    cursorLabels: settings.cursorLabels,
    isOwner: isRoomOwner(name, ownerKey)
  });
}

function handleRoomSettings(req, res) {
  readBody(req, 4096, body => {
    let j;
    try { j = JSON.parse(body); } catch (e) { return json(res, 400, { error: 'Requête invalide' }); }
    const name = String(j.room || '');
    if (!ROOM_STRICT.test(name)) return json(res, 400, { error: 'Nom de salle invalide' });
    const settings = roomSettings[name];
    if (!settings || !isRoomOwner(name, j.ownerKey)) return json(res, 403, { error: 'Droits du créateur requis' });
    const ownerName = String(j.ownerName || '').trim().slice(0, 20);
    if (!ownerName || typeof j.ownerLocked !== 'boolean' || typeof j.cursorLabels !== 'boolean') {
      return json(res, 400, { error: 'Réglages invalides' });
    }
    const previous = { ...settings };
    settings.ownerName = ownerName;
    settings.ownerLocked = j.ownerLocked;
    settings.cursorLabels = j.cursorLabels;
    try {
      saveRoomSettings();
      syncRoomSettings(name, openRoom(name));
    } catch (e) {
      roomSettings[name] = previous;
      console.error(e);
      return json(res, 500, { error: 'Enregistrement des réglages impossible' });
    }
    json(res, 200, {
      ownerName: settings.ownerName,
      ownerLocked: settings.ownerLocked,
      cursorLabels: settings.cursorLabels,
      isOwner: true
    });
  });
}

function passwordState(pw) {
  if (!ADMIN_PW) return 'disabled';
  const a = crypto.createHash('sha256').update(String(pw || '')).digest();
  const b = crypto.createHash('sha256').update(ADMIN_PW).digest();
  return crypto.timingSafeEqual(a, b) ? 'ok' : 'bad';
}

function handleLock(req, res) {
  readBody(req, 4096, body => {
    let j;
    try { j = JSON.parse(body); } catch (e) { return json(res, 400, { error: 'Requête invalide' }); }
    const st = passwordState(j.password);
    if (st === 'disabled') return json(res, 403, { error: "Administration désactivée : aucun mot de passe n'est défini sur le serveur" });
    if (st === 'bad') return setTimeout(() => json(res, 401, { error: 'Mot de passe incorrect' }), 1000);   // freine les essais
    const name = String(j.room || '');
    if (!ROOM_STRICT.test(name)) return json(res, 400, { error: 'Nom de salle invalide (lettres, chiffres, - et _ uniquement)' });
    if (!docs.has(name) && !locked.has(name)) return json(res, 404, { error: 'Salle inconnue' });
    try {
      if (j.locked) lockRoom(name); else unlockRoom(name);
    } catch (e) {
      console.error(e);
      return json(res, 500, { error: 'Erreur du serveur : ' + e.message });
    }
    json(res, 200, { ok: true, room: name, locked: !!j.locked });
  });
}

const server = http.createServer((req, res) => {
  const requestUrl = new URL(req.url, 'http://localhost');
  const url = requestUrl.pathname;
  if (url === '/_room/create' && req.method === 'POST') return handleCreateRoom(req, res);
  if (url === '/_room/state' && req.method === 'GET') return handleRoomState(req, res);
  if (url === '/_room/settings' && req.method === 'POST') return handleRoomSettings(req, res);
  if (url === '/_rooms' && req.method === 'GET') {
    const names = new Set(docs.keys());
    locked.forEach(n => names.add(n));
    const list = Array.from(names).map(name => ({
      name, users: docs.has(name) ? docs.get(name).conns.size : 0, locked: locked.has(name)
    }));
    list.sort((a, b) => b.users - a.users || a.name.localeCompare(b.name));
    return json(res, 200, list);
  }
  if (url === '/_admin/lock' && req.method === 'POST') return handleLock(req, res);
  res.writeHead(200, { 'Content-Type': 'text/plain' });
  res.end('classroom4python sync server OK');
});

const wss = new WebSocket.Server({ noServer: true });
server.on('upgrade', (req, socket, head) => {
  const requestUrl = new URL(req.url || '/', 'http://localhost');
  let name = requestUrl.pathname.slice(1);
  try { name = decodeURIComponent(name); } catch (e) { /* nom brut */ }
  const owner = isRoomOwner(name, requestUrl.searchParams.get('ownerKey'));
  wss.handleUpgrade(req, socket, head, ws => {
    openRoom(name);
    setupWSConnection(ws, req, { docName: name });
    // Les salles verrouillées et les modifications des non-créateurs sont refusées côté serveur.
    const listeners = ws.listeners('message');
    ws.removeAllListeners('message');
    ws.on('message', (data, isBinary) => {
      if (locked.has(name) && isDocWrite(data)) return;
      if (roomSettings[name] && roomSettings[name].ownerLocked && !owner && isDocWrite(data)) return;
      listeners.forEach(l => l.call(ws, data, isBinary));
    });
  });
});

server.listen(PORT, HOST, () => console.log('Yjs server on ' + HOST + ':' + PORT +
  ' | données : ' + DATA_DIR + ' | salles verrouillées : ' + locked.size +
  ' | administration ' + (ADMIN_PW ? 'activée' : 'DÉSACTIVÉE (PT_ADMIN_PASSWORD absent)')));
