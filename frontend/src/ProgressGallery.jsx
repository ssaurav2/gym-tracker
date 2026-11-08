import React, { useEffect, useRef, useState } from 'react';

async function photoRequest(path, options = {}) {
  const response = await fetch(`/progress-photos${path}`, options);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Couldn’t complete that. Please check the photo and retry.');
  }
  return response.status === 204 ? null : response.json();
}

function dateLabel(value) {
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function PhotoViewer({ photo, onClose, onDelete, busy, error }) {
  const dialog = useRef(null);
  useEffect(() => {
    dialog.current.showModal();
  }, []);
  return <dialog ref={dialog} className="photo-viewer" aria-labelledby="photo-viewer-heading" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <div className="section-heading"><h2 id="photo-viewer-heading">{dateLabel(photo.uploaded_at)}{photo.category ? ` · ${photo.category}` : ''}</h2><button type="button" className="small-button" disabled={busy} onClick={onClose} autoFocus>Close</button></div>
    <img src={`/progress-photos/${photo.id}/image`} alt={`Progress photo uploaded ${dateLabel(photo.uploaded_at)}${photo.category ? `, ${photo.category} view` : ''}`} />
    {error && <p className="error" role="alert">{error}</p>}
    <button type="button" className="small-button delete-button viewer-delete" disabled={busy} onClick={() => onDelete(photo)}>{busy ? 'Deleting…' : 'Delete photo'}</button>
  </dialog>;
}

export default function ProgressGallery() {
  const [photos, setPhotos] = useState([]);
  const [sort, setSort] = useState('newest');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [reload, setReload] = useState(0);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState('');
  const [category, setCategory] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [viewing, setViewing] = useState(null);
  const fileInput = useRef(null);
  const trigger = useRef(null);
  const galleryHeading = useRef(null);

  useEffect(() => {
    let active = true;
    setLoading(true); setLoadError('');
    photoRequest(`?sort=${sort}`).then(data => { if (active) setPhotos(data); })
      .catch(error => { if (active) setLoadError(error.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [sort, reload]);
  useEffect(() => {
    if (!file) { setPreview(''); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function chooseFile(event) {
    const selected = event.target.files[0];
    setActionError(''); setMessage(''); setFile(null);
    if (!selected) return;
    if (!['image/jpeg', 'image/png'].includes(selected.type) || selected.size > 10 * 1024 * 1024) {
      setActionError('Choose a JPEG or PNG photo smaller than 10 MB.');
      event.target.value = ''; return;
    }
    setFile(selected);
  }
  async function upload(event) {
    event.preventDefault();
    if (busy || !file) return;
    setBusy(true); setActionError(''); setMessage('');
    const body = new FormData();
    body.append('file', file);
    if (category) body.append('category', category);
    try {
      await photoRequest('', { method: 'POST', body });
      setFile(null); setCategory(''); fileInput.current.value = '';
      setMessage('Photo added. Keep showing up.'); setReload(value => value + 1);
    } catch (error) { setActionError(error.message); }
    finally { setBusy(false); }
  }
  function closeViewer() {
    setViewing(null);
    trigger.current?.focus();
  }
  async function remove(photo) {
    if (busy || !window.confirm(`Delete this progress photo from ${dateLabel(photo.uploaded_at)}? This cannot be undone.`)) return;
    setBusy(true); setActionError(''); setMessage('');
    try {
      await photoRequest(`/${photo.id}`, { method: 'DELETE' });
      setPhotos(items => items.filter(item => item.id !== photo.id));
      setViewing(null); setMessage('Photo deleted.');
      requestAnimationFrame(() => galleryHeading.current?.focus());
    } catch (error) { setActionError(error.message); }
    finally { setBusy(false); }
  }

  return <>
    <form className="card photo-upload" onSubmit={upload}>
      <p className="eyebrow">A CHECK-IN FOR YOUR FUTURE SELF</p>
      <h1 className="photo-title">to you, <strong>2000 years from now</strong></h1>
      <p className="muted">A moment of progress. Just for you.</p>
      <label htmlFor="progress-file">Add a progress photo</label>
      <input ref={fileInput} id="progress-file" type="file" accept="image/jpeg,image/png" onChange={chooseFile} disabled={busy || Boolean(loadError)} aria-describedby="photo-file-hint" />
      <p id="photo-file-hint" className="field-hint">JPEG or PNG · up to 10 MB · upload date saved automatically</p>
      {preview && <img className="upload-preview" src={preview} alt="Selected photo preview" />}
      <label htmlFor="photo-category">View (optional)</label>
      <select id="photo-category" value={category} disabled={busy} onChange={event => setCategory(event.target.value)}><option value="">No category</option><option value="front">Front</option><option value="back">Back</option><option value="side">Side</option></select>
      <button className="primary-button add-button" disabled={!file || busy || loading || Boolean(loadError)}>{busy ? 'Working…' : 'Add photo'}<span aria-hidden="true">+</span></button>
      <p className="muted photo-privacy">Stored on this computer. Photo access is local-only until account protection is added.</p>
    </form>
    {actionError && !viewing && <p className="error" role="alert">{actionError}</p>}
    {message && <p className="success" role="status">{message}</p>}
    <section className="photo-gallery" aria-labelledby="gallery-heading">
      <p className="eyebrow">YOUR PROGRESS, OVER TIME</p>
      <h2 ref={galleryHeading} tabIndex={-1} className="photo-title" id="gallery-heading">from you, <strong>2000 years ago</strong></h2>
      <label htmlFor="photo-sort">Photo order</label><select id="photo-sort" value={sort} disabled={busy} onChange={event => setSort(event.target.value)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option></select>
      {loadError ? <div className="error-banner photo-load-error" role="alert">{loadError}<button type="button" className="text-button" onClick={() => setReload(value => value + 1)}>Retry</button></div> : loading ? <p className="muted" role="status">Loading photos…</p> : !photos.length ? <div className="card empty-list photo-empty"><h3>Your story starts here.</h3><p className="muted">Add your first progress photo above.</p></div> : <ul className="photo-grid">{photos.map(photo => <li key={photo.id} className="photo-tile">
        <button type="button" className="photo-open" disabled={busy} onClick={event => { trigger.current = event.currentTarget; setViewing(photo); }} aria-label={`Open photo from ${dateLabel(photo.uploaded_at)}${photo.category ? `, ${photo.category} view` : ''}`}>
          <img src={`/progress-photos/${photo.id}/image`} loading="lazy" alt={`${photo.category || 'Progress'} photo`} />
          <span className="photo-meta"><time dateTime={photo.uploaded_at}>{dateLabel(photo.uploaded_at)}</time>{photo.category && <span className="photo-category">{photo.category}</span>}</span>
        </button>
        <button type="button" className="text-button delete-button photo-delete" disabled={busy} onClick={() => remove(photo)} aria-label={`Delete photo from ${dateLabel(photo.uploaded_at)}`}>Delete</button>
      </li>)}</ul>}
    </section>
    {viewing && <PhotoViewer photo={viewing} onClose={closeViewer} onDelete={remove} busy={busy} error={actionError} />}
  </>;
}
