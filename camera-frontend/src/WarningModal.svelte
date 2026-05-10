<script>
  export let warning;
  export let onClose;
  export let onPositionChange;

  let isDragging = false;
  let offset = { x: 0, y: 0 };

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
      onPositionChange(warning.id, x, y);
    }
  }
</script>

<svelte:window on:mousemove={handleMouseMove} on:mouseup={handleMouseUp} />

<div class="modal-box" style="left: {x}px; top: {y}px;">
  <div class="handle" on:mousedown={handleMouseDown}>
    <span>{warning.icon} Details</span>
    <button class="close" on:click={onClose}>&times;</button>
  </div>

  <div class="content">
    <img src={warning.imageUrl} alt="issue" draggable="false" />
    <h4>{warning.title}</h4>
    <p><strong>Issue:</strong> {warning.issue}</p>
    <p class="fix"><strong>Fix:</strong> {warning.fix}</p>
  </div>
</div>

<style>
  .modal-box {
    position: fixed;
    width: 280px;
    background: white;
    border: 1px solid #444;
    box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    border-radius: 8px;
    z-index: 2000;
    user-select: none;
  }
  .handle {
    padding: 10px;
    background: #333;
    color: white;
    cursor: grab;
    display: flex;
    justify-content: space-between;
    border-radius: 7px 7px 0 0;
  }
  .handle:active { cursor: grabbing; }
  .content { padding: 15px; }
  img { width: 100%; border-radius: 4px; margin-bottom: 10px; }
  h4 { margin: 0 0 10px 0; color: #d32f2f; }
  p { font-size: 0.85rem; margin: 5px 0; }
  .fix { color: #2e7d32; font-weight: bold; margin-top: 10px; border-top: 1px solid #eee; padding-top: 5px; }
  .close { background: none; border: none; color: white; cursor: pointer; font-size: 1.2rem; }
</style>