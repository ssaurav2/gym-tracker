// Account boundaries are synchronous; Supabase callbacks never await SDK calls.
export class AccountChangedError extends Error {
  constructor() { super('The account changed. Please try again.'); }
}

export function localDateString(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

export class AccountSession {
  constructor(auth, fetcher = (...args) => fetch(...args)) {
    this.auth = auth;
    this.fetcher = fetcher;
    this.snapshot = { session: null, ready: false, epoch: 0, notice: '', signingOut: false };
    this.listeners = new Set();
    this.pending = new Set();
    this.events = 0;
    this.loginAttempt = 0;
    this.blockSession = false;
    this.signingOut = false;
    this.loggingIn = false;
  }

  getSnapshot = () => this.snapshot;
  subscribe = listener => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  apply(session, notice = '', force = false) {
    if (!session?.user?.id || !session?.access_token) session = null;
    const changed = force || this.snapshot.session?.user.id !== session?.user.id;
    if (changed) {
      for (const controller of this.pending) controller.abort();
      this.pending.clear();
    }
    this.snapshot = { session, ready: true, epoch: this.snapshot.epoch + (changed ? 1 : 0), notice, signingOut: this.signingOut };
    for (const listener of this.listeners) listener();
  }

  start() {
    let active = true;
    const observedEvents = this.events;
    const { data: { subscription } } = this.auth.onAuthStateChange((_event, session) => {
      if (!active) return;
      this.events += 1;
      if (!session) {
        this.blockSession = true;
        this.apply(null, this.snapshot.notice);
      } else if (!this.blockSession && !this.signingOut && !this.loggingIn) this.apply(session);
    });
    this.auth.getSession().then(({ data, error }) => {
      if (!active || this.events !== observedEvents || this.blockSession) return;
      this.apply(error ? null : data.session, error ? 'Please log in again.' : '');
    }).catch(() => {
      if (active && this.events === observedEvents) this.apply(null, 'Please log in again.');
    });
    return () => {
      active = false;
      subscription.unsubscribe();
      for (const controller of this.pending) controller.abort();
      this.pending.clear();
    };
  }

  async login(email, password) {
    if (this.signingOut) throw new Error('Finishing logout. Please try again in a moment.');
    const attempt = ++this.loginAttempt;
    this.loggingIn = true;
    this.blockSession = true;
    this.apply(null, '', true);
    try {
      const { data, error } = await this.auth.signInWithPassword({ email: email.trim(), password });
      if (attempt !== this.loginAttempt) throw new AccountChangedError();
      if (error || !data?.session?.user?.id || !data.session.access_token) throw new Error('Login failed');
      this.blockSession = false;
      this.apply(data.session);
    } catch (error) {
      if (attempt !== this.loginAttempt || error instanceof AccountChangedError) throw new AccountChangedError();
      this.blockSession = true;
      this.apply(null);
      throw new Error('Couldn’t log in. Check your email and password, then try again.');
    } finally {
      if (attempt === this.loginAttempt) this.loggingIn = false;
    }
  }

  async signOut(notice = '') {
    this.loginAttempt += 1;
    this.loggingIn = false;
    this.blockSession = true;
    this.signingOut = true;
    this.apply(null, notice, true); // Clears account data immediately, even offline.
    try {
      const { error } = await this.auth.signOut({ scope: 'local' });
      if (error) this.apply(null, 'Signed out on this browser. The server could not be reached.');
    } catch {
      this.apply(null, 'Signed out on this browser. The server could not be reached.');
    } finally {
      this.signingOut = false;
      this.apply(null, this.snapshot.notice);
    }
  }

  isCurrent(epoch, userId) {
    return Boolean(userId) && !this.blockSession && this.snapshot.epoch === epoch && this.snapshot.session?.user.id === userId;
  }

  expire(epoch, userId) {
    if (!this.isCurrent(epoch, userId)) return;
    void this.signOut('Your login expired. Please log in again.');
  }

  createRequest(epoch, userId) {
    const assertCurrent = () => {
      if (!this.isCurrent(epoch, userId)) throw new AccountChangedError();
    };
    return async (path, body, method = body === undefined ? 'GET' : 'POST') => {
      assertCurrent();
      // Never attach a token to an external URL or another service.
      if (!/^\/(exercises|sets)([/?]|$)/.test(path)) throw new Error('Unsupported API path.');
      const controller = new AbortController();
      this.pending.add(controller);
      try {
        let current;
        try { current = await this.auth.getSession(); }
        catch {
          assertCurrent();
          this.expire(epoch, userId);
          throw new AccountChangedError();
        }
        const { data, error } = current;
        assertCurrent();
        if (error || !data?.session?.access_token || data.session.user?.id !== userId) {
          this.expire(epoch, userId);
          throw new AccountChangedError();
        }
        const response = await this.fetcher(path, {
          method, signal: controller.signal, cache: 'no-store',
          headers: { Authorization: `Bearer ${data.session.access_token}`,
            ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
          ...(body === undefined ? {} : { body: JSON.stringify(body) }),
        });
        assertCurrent();
        if (response.status === 401) {
          this.expire(epoch, userId);
          throw new AccountChangedError();
        }
        const result = response.status === 204 ? null : await response.json().catch(() => null);
        assertCurrent();
        if (!response.ok) {
          throw new Error(typeof result?.detail === 'string' ? result.detail : 'Couldn’t save that. Check your entries and try again.');
        }
        return result;
      } catch (error) {
        if (!this.isCurrent(epoch, userId)) throw new AccountChangedError();
        if (error instanceof AccountChangedError) throw error;
        if (error instanceof TypeError) throw new Error('Couldn’t reach the server. Please try again.');
        throw error;
      } finally {
        this.pending.delete(controller);
      }
    };
  }
}
