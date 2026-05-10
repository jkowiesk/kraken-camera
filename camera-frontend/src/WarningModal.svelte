<script>
  export let warning;
  export let onClose;
  export let onPositionChange;

  let isDragging = false;
  let offset = { x: 0, y: 0 };

  // Coordinates are kept in local state for smooth dragging
  let x = warning.modalX ?? 100;
  let y = warning.modalY ?? 100;

  function handleMouseDown(e) {
    isDragging = true;
    offset.x = e.clientX - x;
    offset.y = e.clientY - y;
  }

  function handleMouseMove(e) {
    if (!isDragging) return;
    x = e.clientX - offset.x;
    y = e.clientY - offset.y;
  }

  function handleMouseUp() {
    if (isDragging) {
      isDragging = false;
      // Triggers auto-save in App.svelte
      onPositionChange(warning.id, x, y);
    }
  }
</script>

<svelte:window on:mousemove={handleMouseMove} on:mouseup={handleMouseUp} />

<div
  class="modal-box"
  class:info-only={!warning.fix}
  style="left: {x}px; top: {y}px;"
>
  <div class="handle" on:mousedown={handleMouseDown}>
    <div class="title-group">
      <span class="icon">{warning.icon}</span>
      <span class="title">Inspection Detail</span>
    </div>
    <button class="close" on:click={onClose}>&times;</button>
  </div>

  <div class="content">
    <header class="report-header">
      <h3>{warning.title}</h3>
    </header>

    <div class="comparison-grid" class:single-column={!warning.fix}>

      <div class="column">
        <div class="label-badge {warning.fix ? 'red' : 'blue'}">
          {warning.fix ? 'Current Issue' : 'Site Information'}
        </div>
        <div class="media-container">
          <img src={warning.imageUrl} alt="observation" draggable="false" />
        </div>
        <p class="description">{warning.issue}</p>
      </div>

      {#if warning.fixedImageUrl}
        <div class="column">
          <div class="label-badge green">Required Fix</div>
          <div class="media-container">
            {#if warning.fixedImageUrl}
              <img src={warning.fixedImageUrl} alt="fix reference" draggable="false" />
            {:else}
              <div class="placeholder">Reference image pending</div>
            {/if}
          </div>
          <p class="description fix-text">{warning.fix}</p>
        </div>
      {/if}
    </div>
  </div>
</div>

<style>
  /* --- Modal Container --- */
  .modal-box {
    position: fixed;
    width: 620px; /* Width for side-by-side view */
    background: #ffffff;
    border-radius: 12px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    border: 1px solid #d1d5db;
    z-index: 2000;
    overflow: hidden;
    font-family: 'Inter', -apple-system, sans-serif;
    transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  /* Shrinks the box if it's just information (no fix) */
  .modal-box.info-only {
    width: 360px;
  }

  /* --- Header / Drag Handle --- */
  .handle {
    padding: 14px 20px;
    background: #000000;
    color: #ffffff;
    cursor: grab;
    display: flex;
    justify-content: space-between;
    align-items: center;
    user-select: none;
  }

  .handle:active { cursor: grabbing; }

  .title-group { display: flex; align-items: center; gap: 10px; }
  .icon { font-size: 1.2rem; }
  .title { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }

  /* --- Body Content --- */
  .content { padding: 24px; }

  .report-header h3 {
    margin: 0 0 20px 0;
    font-size: 1.15rem;
    color: #111827;
    font-weight: 700;
  }

  /* --- Comparison Grid --- */
  .comparison-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
  }

  .comparison-grid.single-column {
    grid-template-columns: 1fr;
  }

  .column { display: flex; flex-direction: column; }

  /* --- Status Badges --- */
  .label-badge {
    display: inline-block;
    width: fit-content;
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 800;
    text-transform: uppercase;
    margin-bottom: 12px;
  }

  .red { background: #fee2e2; color: #b91c1c; }
  .green { background: #dcfce7; color: #15803d; }
  .blue { background: #e0f2fe; color: #0369a1; }

  /* --- Media Styling --- */
  .media-container {
    width: 100%;
    aspect-ratio: 4/3;
    background: #f3f4f6;
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 12px;
    border: 1px solid #e5e7eb;
  }

  img { width: 100%; height: 100%; object-fit: cover; }

  .placeholder {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #9ca3af;
    font-size: 0.75rem;
    font-style: italic;
  }

  /* --- Text Styling --- */
  .description {
    font-size: 0.875rem;
    color: #4b5563;
    line-height: 1.6;
    margin: 0;
  }

  .fix-text {
    color: #15803d;
    font-weight: 500;
  }

  /* --- Interaction --- */
  .close {
    background: none;
    border: none;
    color: #9ca3af;
    font-size: 1.5rem;
    cursor: pointer;
    transition: color 0.2s;
    line-height: 1;
  }

  .close:hover { color: #ffffff; }
</style>