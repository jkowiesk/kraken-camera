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
    width: 320px;
    background: white;
    border-radius: 12px;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2);
    border: 1px solid #e2e8f0;
    z-index: 2000;
    overflow: hidden;
  }

  .handle {
    padding: 12px 16px;
    background: #000;
    color: white;
    cursor: grab;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .handle span {
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .content {
    padding: 20px;
  }

  img {
    width: 100%;
    height: 180px;
    object-fit: cover;
    border-radius: 6px;
    margin-bottom: 16px;
    background: #f1f5f9;
  }

  h4 {
    margin: 0 0 12px 0;
    font-size: 1.1rem;
    color: #1a202c;
  }

  p {
    font-size: 0.9rem;
    color: #4a5568;
    line-height: 1.6;
    margin: 8px 0;
  }

  strong {
    color: #1a202c;
    font-size: 0.75rem;
    text-transform: uppercase;
    display: block;
    margin-bottom: 2px;
  }

  .fix {
    margin-top: 15px;
    padding-top: 15px;
    border-top: 1px solid #edf2f7;
    color: #2c7a7b; /* Dark teal for the solution */
  }

  .close {
    background: rgba(255,255,255,0.1);
    border: none;
    color: white;
    width: 24px;
    height: 24px;
    border-radius: 4px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .close:hover {
    background: rgba(255,255,255,0.2);
  }
</style>