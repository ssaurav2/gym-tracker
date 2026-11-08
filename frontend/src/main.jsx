import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

async function request(path, body, method = body === undefined ? 'GET' : 'POST') {
  const response = await fetch(path, {
    method, ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Couldn’t save that. Check your entries and try again.');
  }
  return response.status === 204 ? null : response.json();
}

function Icon({ name }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {name === 'history' ? <><path d="M3 11a9 9 0 1 1 2 7M3 4v7h7M12 7v5l3 2" /></> : name === 'lift' ? <><path d="m6 6 12 12M4 8l4-4M2 6l4-4m10 18 4-4m-2 6 4-4M5 11l6-6m2 14 6-6" /></> : name === 'list' ? <><rect x="5" y="4" width="15" height="17" rx="3" /><path d="M9 3h7v4H9zm0 8h7m-7 5h7" /></> : <><circle cx="12" cy="13" r="8" /><path d="M12 9v5l3 2M9 2h6m-3 0v3" /></>}
  </svg>;
}

function RestTimer() {
  const [duration, setDuration] = useState(90);
  const [remaining, setRemaining] = useState(90);
  const [running, setRunning] = useState(false);
  const deadline = useRef(0);
  const [finished, setFinished] = useState(false);
  useEffect(() => {
    if (!running) return;
    const tick = () => {
      const next = Math.max(0, Math.ceil((deadline.current - Date.now()) / 1000));
      setRemaining(next);
      if (!next) { setRunning(false); setFinished(true); }
    };
    tick();
    const interval = setInterval(tick, 250);
    return () => clearInterval(interval);
  }, [running]);
  function toggle() {
    if (running) { setRunning(false); return; }
    const seconds = remaining || duration;
    setRemaining(seconds); setFinished(false);
    deadline.current = Date.now() + seconds * 1000; setRunning(true);
  }
  return <section className="card timer-card" aria-label="Rest timer">
    <div className="section-heading"><span className="eyebrow"><Icon name="timer" /> REST TIMER</span><span className="muted">Take a breath.</span></div>
    <div className="timer-row"><span className="timer-digits" role="timer" aria-label={`${remaining} seconds remaining`}>{Math.floor(remaining / 60)}<span>:</span>{String(remaining % 60).padStart(2, '0')}</span>
      <div className="timer-actions"><button type="button" className="small-button" onClick={toggle}>{running ? 'Pause' : remaining < duration && remaining > 0 ? 'Resume' : 'Start'}</button><button type="button" className="text-button" onClick={() => { setRunning(false); setRemaining(duration); setFinished(false); }}>Reset</button></div>
    </div>
    <div className="timer-presets" aria-label="Rest duration">{[60, 90, 120].map(seconds => <button type="button" key={seconds} className={duration === seconds ? 'chip selected' : 'chip'} aria-pressed={duration === seconds} onClick={() => { setDuration(seconds); setRemaining(seconds); setRunning(false); setFinished(false); }}>{seconds === 60 ? '1 min' : seconds === 90 ? '1.5 min' : '2 min'}</button>)}</div>
    <span className="sr-only" role="status">{finished ? 'Rest complete. Ready for your next set.' : ''}</span>
    {finished && <p className="timer-complete">Rest complete. You’re up.</p>}
  </section>;
}

function History({ exercises, onChange }) {
  const [filter, setFilter] = useState('');
  const [sets, setSets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reload, setReload] = useState(0);
  const [editing, setEditing] = useState(null);
  const [weight, setWeight] = useState('');
  const [reps, setReps] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setLoading(true); setError(''); setEditing(null);
    request(filter ? `/sets?exercise_id=${filter}` : '/sets')
      .then(data => { if (active) setSets(data); })
      .catch(() => { if (active) setError('Couldn’t load history. Please retry.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [filter, reload]);

  async function save(event, entry) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      const updated = await request(`/sets/${entry.id}`, { weight: Number(weight), reps: Number(reps) }, 'PUT');
      setSets(items => items.map(item => item.id === entry.id ? updated : item));
      setEditing(null); setMessage('Set updated.'); onChange();
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }
  async function remove(entry, exerciseName) {
    if (busy || !window.confirm(`Delete ${exerciseName}: ${entry.weight} × ${entry.reps} on ${entry.date}? This cannot be undone.`)) return;
    setBusy(true); setError(''); setMessage('');
    try {
      await request(`/sets/${entry.id}`, undefined, 'DELETE');
      setSets(items => items.filter(item => item.id !== entry.id));
      setMessage('Set deleted.'); onChange();
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }
  // The API supplies newest-first sets; keep that order within each date.
  const setsByDay = new Map();
  for (const entry of sets) {
    if (!setsByDay.has(entry.date)) setsByDay.set(entry.date, []);
    setsByDay.get(entry.date).push(entry);
  }
  const days = [...setsByDay.keys()].sort().reverse();

  return <section aria-label="Logged sets history">
    <div className="card"><label htmlFor="history-exercise">Filter by exercise</label>
      <select id="history-exercise" value={filter} disabled={busy} onChange={event => { setFilter(event.target.value); setMessage(''); }}>
        <option value="">All exercises</option>{exercises.map(exercise => <option key={exercise.id} value={exercise.id}>{exercise.name}</option>)}
      </select>
    </div>
    {error && <div className="error-banner" role="alert">{error}<button type="button" className="text-button" disabled={busy} onClick={() => setReload(value => value + 1)}>Retry history</button></div>}
    {message && <p className="success" role="status">{message}</p>}
    {loading ? <p className="muted" role="status">Loading history…</p> : !error && !sets.length ? <div className="card empty-list"><h2>No sets yet.</h2><p className="muted">{filter ? 'Log a set for this exercise to see it here.' : 'Your logged sets will appear here, newest first.'}</p></div> : !loading && <div className="history-days">{days.map(day => <section className="history-day" key={day} aria-labelledby={`history-day-${day}`}>
      <h2 className="history-day-heading" id={`history-day-${day}`}><time dateTime={day}>{new Date(`${day}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}</time></h2>
      <ul className="history-list">{setsByDay.get(day).map(entry => {
      const exerciseName = exercises.find(exercise => exercise.id === entry.exercise_id)?.name || 'Exercise';
      return <li className="card history-card" key={entry.id}>
        <h3>{exerciseName}</h3>
        {editing === entry.id ? <form onSubmit={event => save(event, entry)}>
          <div className="input-pair"><div><label htmlFor={`history-weight-${entry.id}`}>Weight</label><input id={`history-weight-${entry.id}`} type="number" inputMode="decimal" min="0.01" step="any" value={weight} onChange={event => setWeight(event.target.value)} required disabled={busy} autoFocus /></div>
          <div><label htmlFor={`history-reps-${entry.id}`}>Reps</label><input id={`history-reps-${entry.id}`} type="number" inputMode="numeric" min="1" step="1" value={reps} onChange={event => setReps(event.target.value)} required disabled={busy} /></div></div>
          <div className="history-actions"><button className="small-button" disabled={busy}>{busy ? 'Saving…' : 'Save changes'}</button><button type="button" className="text-button" disabled={busy} onClick={() => setEditing(null)}>Cancel</button></div>
        </form> : <><p className="history-values">{entry.weight} <span>×</span> {entry.reps}<small>weight × reps</small></p>
          <div className="history-actions"><button type="button" className="small-button" disabled={busy} aria-label={`Edit ${exerciseName} set from ${entry.date}`} onClick={() => { setEditing(entry.id); setWeight(String(entry.weight)); setReps(String(entry.reps)); setError(''); setMessage(''); }}>Edit</button>
          <button type="button" className="text-button delete-button" disabled={busy} aria-label={`Delete ${exerciseName} set from ${entry.date}`} onClick={() => remove(entry, exerciseName)}>Delete</button></div></>}
      </li>;
    })}</ul></section>)}</div>}
  </section>;
}

function App() {
  const [screen, setScreen] = useState('log');
  const [exercises, setExercises] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [selected, setSelected] = useState('');
  const [last, setLast] = useState(null);
  const [lastLoading, setLastLoading] = useState(false);
  const [lastError, setLastError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [weight, setWeight] = useState('');
  const [reps, setReps] = useState('');
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState(false);
  const [logMessage, setLogMessage] = useState('');
  const [logError, setLogError] = useState('');
  const [addError, setAddError] = useState('');
  const [addMessage, setAddMessage] = useState('');
  const selectionVersion = useRef(0);

  async function loadExercises() {
    setLoading(true); setLoadError('');
    try { setExercises(await request('/exercises')); }
    catch { setLoadError('Couldn’t load exercises. Check that the Python server is running, then retry.'); }
    finally { setLoading(false); }
  }
  useEffect(() => { loadExercises(); }, []);
  useEffect(() => {
    let active = true;
    setLast(null); setLastError('');
    if (!selected) { setLastLoading(false); return; }
    setLastLoading(true);
    request(`/exercises/${selected}/last-set`).then(data => { if (active) setLast(data); })
      .catch(() => { if (active) setLastError('Couldn’t load your last set.'); })
      .finally(() => { if (active) setLastLoading(false); });
    return () => { active = false; };
  }, [selected, refresh]);

  async function logSet(event) {
    event.preventDefault();
    if (saving || !selected) return;
    setSaving(true); setLogError(''); setLogMessage('');
    const version = selectionVersion.current;
    try {
      await request('/sets', { exercise_id: Number(selected), weight: Number(weight), reps: Number(reps) });
      if (version === selectionVersion.current) { setLogMessage('Set logged. Nice work.'); setRefresh(value => value + 1); }
    } catch (error) { if (version === selectionVersion.current) setLogError(error.message); }
    finally { setSaving(false); }
  }
  async function addExercise(event) {
    event.preventDefault();
    if (adding) return;
    setAdding(true); setAddError(''); setAddMessage('');
    try {
      const exercise = await request('/exercises', { name: name.trim() });
      setExercises(items => [...items, exercise]); setName(''); setAddMessage(`${exercise.name} added.`);
      if (!selected) { setSelected(String(exercise.id)); selectionVersion.current += 1; }
    } catch (error) { setAddError(error.message); }
    finally { setAdding(false); }
  }
  return <div className="app-shell">
    <header className="brand"><span className="brand-mark"><Icon name="lift" /></span><span>GYM<span className="brand-light">TRACKER</span></span><span className="brand-tag">ONE SET AT A TIME</span></header>
    <main>
      <div className="page-heading"><p className="eyebrow">{screen === 'log' ? 'SHOW UP. BUILD ON IT.' : screen === 'history' ? 'EVERY SET ADDS UP.' : 'YOUR LIFTS, YOUR WAY.'}</p><h1>{screen === 'log' ? <>Make your<br /><strong>next set count.</strong></> : screen === 'history' ? <>Look back.<br /><strong>Keep building.</strong></> : <>Build your<br /><strong>exercise list.</strong></>}</h1><p className="intro">{screen === 'log' ? 'A little stronger, one set at a time.' : screen === 'history' ? 'Your logged sets, newest first.' : 'Keep your go-to movements close.'}</p></div>
      {loadError && <div className="error-banner" role="alert">{loadError}<button type="button" className="text-button" onClick={loadExercises}>Retry</button></div>}
      {screen === 'log' ? <>
        <form className="card log-card" onSubmit={logSet}>
          <div className="section-heading"><h2>Log a set</h2><span className="today-dot">Today</span></div>
          <label htmlFor="exercise">Exercise</label>
          <select id="exercise" value={selected} disabled={loading || saving || !exercises.length} required onChange={event => { setSelected(event.target.value); selectionVersion.current += 1; setLogMessage(''); setLogError(''); }}>
            <option value="">{loading ? 'Loading exercises…' : 'Choose an exercise'}</option>{exercises.map(exercise => <option key={exercise.id} value={exercise.id}>{exercise.name}</option>)}
          </select>
          {!loading && !loadError && !exercises.length && <p className="empty-hint">Your first set starts with an exercise. <button type="button" className="inline-button" onClick={() => setScreen('exercises')}>Add one →</button></p>}
          <div className="last-set" aria-live="polite"><span className="eyebrow">LAST TIME</span>{lastLoading ? <p className="last-placeholder">Loading your last set…</p> : lastError ? <p className="last-placeholder">{lastError} <button type="button" className="inline-button" onClick={() => setRefresh(value => value + 1)}>Retry</button></p> : last ? <p className="last-value">{last.weight} <span>×</span> {last.reps}<small>weight × reps</small></p> : <p className="last-placeholder">{selected ? 'No sets yet. Set your starting point.' : 'Choose a lift to see your last set.'}</p>}</div>
          <div className="input-pair"><div><label htmlFor="weight">Weight</label><input id="weight" type="number" inputMode="decimal" min="0.01" step="any" placeholder="0" value={weight} onChange={event => { setWeight(event.target.value); setLogMessage(''); }} required /></div><div><label htmlFor="reps">Reps</label><input id="reps" type="number" inputMode="numeric" min="1" step="1" placeholder="0" value={reps} onChange={event => { setReps(event.target.value); setLogMessage(''); }} required /></div></div>
          <p className="field-hint">Use your usual weight unit consistently.</p>
          {logError && <p className="error" role="alert">{logError}</p>}{logMessage && <p className="success" role="status">{logMessage}</p>}
          <button className="primary-button" disabled={saving || !selected || loading || !weight || !reps}>{saving ? 'Logging…' : 'Log Set'}<span aria-hidden="true">↗</span></button>
        </form>
      </> : screen === 'history' ? <History exercises={exercises} onChange={() => setRefresh(value => value + 1)} /> : <>
        <form className="card" onSubmit={addExercise}><h2>Add an exercise</h2><label htmlFor="new-exercise">Exercise name</label><input id="new-exercise" placeholder="e.g. Bench Press" maxLength={120} value={name} onChange={event => { setName(event.target.value); setAddMessage(''); }} required />{addError && <p className="error" role="alert">{addError}</p>}{addMessage && <p className="success" role="status">{addMessage}</p>}<button className="primary-button add-button" disabled={adding || loading || Boolean(loadError) || !name.trim()}>{adding ? 'Adding…' : 'Add Exercise'}<span aria-hidden="true">+</span></button></form>
        <section className="exercise-section"><div className="section-heading"><h2>Your exercises</h2><span className="count">{exercises.length}</span></div>{loading ? <p className="muted" role="status">Loading exercises…</p> : !exercises.length ? <div className="card empty-list"><Icon name="lift" /><h3>Your list starts here.</h3><p className="muted">Add your first exercise above.</p></div> : <ul className="exercise-list">{exercises.map((exercise, index) => <li key={exercise.id}><span className="exercise-number">{String(index + 1).padStart(2, '0')}</span><span className="exercise-name">{exercise.name}</span><button type="button" className="exercise-go" aria-label={`Log a set of ${exercise.name}`} onClick={() => { setSelected(String(exercise.id)); selectionVersion.current += 1; setLogMessage(''); setLogError(''); setScreen('log'); }}>↗</button></li>)}</ul>}</section>
      </>}
      <div hidden={screen !== 'log'}><RestTimer /><p className="footer-note">Small steps. Stronger you.</p></div>
    </main>
    <nav className="bottom-nav" aria-label="Main navigation">{[['log', 'lift', 'Log a Set'], ['exercises', 'list', 'Exercises'], ['history', 'history', 'History']].map(([key, icon, label]) => <button type="button" key={key} className={screen === key ? 'nav-item active' : 'nav-item'} aria-current={screen === key ? 'page' : undefined} onClick={() => setScreen(key)}><span className="nav-icon"><Icon name={icon} /></span><span>{label}</span></button>)}</nav>
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
