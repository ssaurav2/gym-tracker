import assert from 'node:assert/strict';
import { test } from 'node:test';
import { AccountChangedError, AccountSession, localDateString } from '../src/accountSession.js';
import { frontendConfiguration } from '../src/frontendConfiguration.js';

const A = { user: { id: 'account-a', email: 'a@example.invalid' }, access_token: 'test-token-a' };
const B = { user: { id: 'account-b', email: 'b@example.invalid' }, access_token: 'test-token-b' };
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function response(data, status = 200) {
  return { status, ok: status >= 200 && status < 300, json: async () => data };
}
class FakeAuth {
  constructor(session = null) { this.session = session; this.listeners = new Set(); this.signOutCalls = []; }
  onAuthStateChange(callback) {
    this.listeners.add(callback);
    return { data: { subscription: { unsubscribe: () => this.listeners.delete(callback) } } };
  }
  emit(event, session) {
    this.session = session;
    for (const listener of this.listeners) listener(event, session);
  }
  async getSession() { return { data: { session: this.session }, error: null }; }
  async signInWithPassword(credentials) {
    this.loginCredentials = credentials;
    const session = credentials.email === B.user.email ? B : A;
    this.emit('SIGNED_IN', session);
    return { data: { session }, error: null };
  }
  async signOut(options) {
    this.signOutCalls.push(options);
    this.emit('SIGNED_OUT', null);
    return { error: null };
  }
}
async function active(t, fetcher, session = A) {
  const auth = new FakeAuth(session);
  const store = new AccountSession(auth, fetcher);
  t.after(store.start());
  await tick();
  const request = store.createRequest(store.getSnapshot().epoch, session?.user.id);
  return { auth, store, request };
}

test('login trims email, never trims password, and sends no signup/reset operation', async t => {
  const { auth, store } = await active(t, () => assert.fail('No API call expected'), null);
  await store.login(' b@example.invalid ', ' keep spaces ');
  assert.deepEqual(auth.loginCredentials, { email: B.user.email, password: ' keep spaces ' });
  assert.equal(store.getSnapshot().session.user.id, B.user.id);
});

test('login errors are generic and do not expose SDK error details', async t => {
  const { auth, store } = await active(t, () => assert.fail('No API call expected'), null);
  auth.signInWithPassword = async () => ({ error: new Error('SENSITIVE_EXCEPTION'), data: null });
  await assert.rejects(store.login(A.user.email, 'test-password'), error => {
    assert.equal(error.message.includes('SENSITIVE_EXCEPTION'), false);
    return true;
  });
  assert.equal(store.getSnapshot().session, null);
});

test('all API methods send the fresh bearer token with no-store', async t => {
  const calls = [];
  const { store, request } = await active(t, async (...args) => { calls.push(args); return response({ id: 1 }); });
  await request('/exercises');
  await request('/sets', { weight: 100, reps: 8, date: '2026-11-11' });
  await request('/sets/1', { weight: 105, reps: 9 }, 'PUT');
  await request('/sets/1', undefined, 'DELETE');
  assert.deepEqual(calls.map(([, options]) => options.method), ['GET', 'POST', 'PUT', 'DELETE']);
  for (const [, options] of calls) {
    assert.equal(options.headers.Authorization, `Bearer ${A.access_token}`);
    assert.equal(options.cache, 'no-store');
    assert.equal(options.signal.aborted, false);
  }
  assert.equal(store.pending.size, 0);
});

test('refreshing one account uses its new token without resetting its view key', async t => {
  let sent;
  const { auth, store, request } = await active(t, async (_path, options) => { sent = options; return response([]); });
  const epoch = store.getSnapshot().epoch;
  auth.emit('TOKEN_REFRESHED', { ...A, access_token: 'refreshed-test-token' });
  await request('/sets');
  assert.equal(store.getSnapshot().epoch, epoch);
  assert.equal(sent.headers.Authorization, 'Bearer refreshed-test-token');
});

test('an account switch changes the view key and invalidates the old request function', async t => {
  let calls = 0;
  const { auth, store, request } = await active(t, async () => { calls++; return response([]); });
  const epoch = store.getSnapshot().epoch;
  auth.emit('SIGNED_IN', B);
  assert.notEqual(store.getSnapshot().epoch, epoch);
  await assert.rejects(request('/sets'), AccountChangedError);
  assert.equal(calls, 0);
});

test('a logout immediately clears session and aborts work before server logout finishes', async t => {
  const fetched = deferred(), signedOut = deferred();
  let signal;
  const { auth, store, request } = await active(t, async (_path, options) => { signal = options.signal; return fetched.promise; });
  const pending = request('/sets');
  await tick();
  auth.signOut = () => signedOut.promise;
  const ending = store.signOut();
  assert.equal(store.getSnapshot().session, null);
  assert.equal(store.getSnapshot().signingOut, true);
  assert.equal(signal.aborted, true);
  await assert.rejects(store.login(B.user.email, 'test-password'), /Finishing logout/);
  signedOut.resolve({ error: null });
  await ending;
  fetched.resolve(response([{ id: 'old-account-record' }]));
  await assert.rejects(pending, AccountChangedError);
  assert.equal(store.getSnapshot().signingOut, false);
});

test('a late response from A cannot display data or sign out newly logged-in B', async t => {
  const fetched = deferred();
  const { auth, store, request } = await active(t, async () => fetched.promise);
  const pending = request('/sets');
  await tick();
  await store.signOut();
  await store.login(B.user.email, 'test-password');
  fetched.resolve(response({ detail: 'old error' }, 401));
  await assert.rejects(pending, AccountChangedError);
  assert.equal(store.getSnapshot().session.user.id, B.user.id);
  assert.equal(auth.signOutCalls.length, 1);
});

test('an account switch while reading JSON also rejects the old result', async t => {
  const decoded = deferred();
  const { auth, request } = await active(t, async () => ({ status: 200, ok: true, json: () => decoded.promise }));
  const pending = request('/sets');
  await tick();
  auth.emit('SIGNED_IN', B);
  decoded.resolve([{ id: 'account-a-only' }]);
  await assert.rejects(pending, AccountChangedError);
});

test('account switch while awaiting SDK session never sends A request using B token', async t => {
  const session = deferred();
  let calls = 0;
  const { auth, request } = await active(t, async () => { calls++; return response([]); });
  auth.getSession = () => session.promise;
  const pending = request('/sets');
  auth.emit('SIGNED_IN', B);
  session.resolve({ data: { session: B }, error: null });
  await assert.rejects(pending, AccountChangedError);
  assert.equal(calls, 0);
});

test('SDK account mismatch fails closed even if its auth event was missed', async t => {
  let calls = 0;
  const { auth, store, request } = await active(t, async () => { calls++; return response([]); });
  auth.getSession = async () => ({ data: { session: B }, error: null });
  await assert.rejects(request('/sets'), AccountChangedError);
  assert.equal(store.getSnapshot().session, null);
  assert.equal(calls, 0);
});

test('401 clears account data and uses local sign-out', async t => {
  const { auth, store, request } = await active(t, async () => response({}, 401));
  await assert.rejects(request('/sets'), AccountChangedError);
  await tick();
  assert.equal(store.getSnapshot().session, null);
  assert.deepEqual(auth.signOutCalls, [{ scope: 'local' }]);
  assert.match(store.getSnapshot().notice, /expired/);
});

test('offline logout still clears data and ignores stale SDK sessions', async t => {
  const { auth, store } = await active(t, () => assert.fail('No API call expected'));
  auth.signOut = async () => { throw new Error('SENSITIVE_EXCEPTION'); };
  await store.signOut();
  auth.emit('SIGNED_IN', A);
  assert.equal(store.getSnapshot().session, null);
  assert.equal(store.getSnapshot().notice.includes('SENSITIVE_EXCEPTION'), false);
  await store.login(B.user.email, 'test-password');
  assert.equal(store.getSnapshot().session.user.id, B.user.id);
});

test('late bootstrap cannot overwrite a more recent auth event', async t => {
  for (const synchronous of [false, true]) {
    const auth = new FakeAuth();
    const initial = deferred();
    auth.getSession = () => initial.promise;
    if (synchronous) {
      const subscribe = auth.onAuthStateChange.bind(auth);
      auth.onAuthStateChange = callback => {
        const result = subscribe(callback);
        auth.emit('SIGNED_IN', B);
        return result;
      };
    }
    const store = new AccountSession(auth);
    t.after(store.start());
    if (!synchronous) auth.emit('SIGNED_IN', B);
    initial.resolve({ data: { session: A }, error: null });
    await tick();
    assert.equal(store.getSnapshot().session.user.id, B.user.id);
  }
});

test('SDK session errors clear account state without exposing their details', async t => {
  const { auth, store, request } = await active(t, () => assert.fail('No API call expected'));
  auth.getSession = async () => { throw new Error('SENSITIVE_EXCEPTION'); };
  await assert.rejects(request('/sets'), AccountChangedError);
  assert.equal(store.getSnapshot().session, null);
});

test('tokens are never sent to external or unsupported URLs', async t => {
  const { request } = await active(t, () => assert.fail('No fetch expected'));
  for (const path of ['https://evil.invalid/sets', '//evil.invalid/sets', '/progress-photos']) {
    await assert.rejects(request(path), /Unsupported API path/);
  }
});

test('204 responses are not parsed as JSON', async t => {
  const { request } = await active(t, async () => ({ status: 204, ok: true, json: () => assert.fail('No JSON expected') }));
  assert.equal(await request('/sets/1', undefined, 'DELETE'), null);
});

test('local dates use local calendar fields including year boundaries', () => {
  assert.equal(localDateString(new Date(2026, 0, 1, 0, 30)), '2026-01-01');
  assert.equal(localDateString(new Date(2026, 11, 31, 23, 59)), '2026-12-31');
  const local = { getFullYear: () => 2026, getMonth: () => 0, getDate: () => 1,
    toISOString: () => assert.fail('Do not use UTC to choose the local logging date') };
  assert.equal(localDateString(local), '2026-01-01');
});

test('frontend config accepts only a public key and never echoes invalid values', () => {
  assert.equal(frontendConfiguration(), null);
  assert.deepEqual(frontendConfiguration('https://project.invalid/', 'sb_publishable_placeholder'),
    { url: 'https://project.invalid', key: 'sb_publishable_placeholder' });
  for (const [url, key] of [['https://project.invalid', 'sb_secret_SENSITIVE'],
                           ['https://project.invalid', 'eyJ_LEGACY_SERVICE_ROLE'],
                           ['http://project.invalid', 'sb_publishable_placeholder'],
                           ['https://SENSITIVE@project.invalid', 'sb_publishable_placeholder'],
                           ['https://project.invalid/path', 'sb_publishable_placeholder']]) {
    assert.throws(() => frontendConfiguration(url, key), error => {
      assert.equal(error.message.includes(key), false);
      assert.equal(error.message.includes(url), false);
      return true;
    });
  }
});


test('stale SDK sign-in events cannot display a previous user during a new login', async t => {
  const { auth, store } = await active(t, () => assert.fail('No API call expected'), null);
  const pending = deferred();
  auth.signInWithPassword = () => pending.promise;
  const loggingIn = store.login(B.user.email, 'test-password');
  auth.emit('SIGNED_IN', A);
  assert.equal(store.getSnapshot().session, null);
  pending.resolve({ data: { session: B }, error: null });
  await loggingIn;
  assert.equal(store.getSnapshot().session.user.id, B.user.id);
});
