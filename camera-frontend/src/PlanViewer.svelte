<script>
  export let planUrl;
  export let warnings = [];
  export let onWarningClick;
  export let onPositionUpdate;

  let container;
  let draggingId = null;
  let hasMoved = false;

  function handleMouseDown(e, id) {
    e.stopPropagation();
    draggingId = id;
    hasMoved = false;
  }

  function handleMouseMove(e) {
    if (draggingId === null || !container) return;
    hasMoved = true;

    const rect = container.getBoundingClientRect();
    let newX = ((e.clientX - rect.left) / rect.width) * 100;
    let newY = ((e.clientY - rect.top) / rect.height) * 100;

    // Constrain 0-100%
    newX = Math.max(0, Math.min(100, newX));
    newY = Math.max(0, Math.min(100, newY));

    onPositionUpdate(draggingId, newX, newY);
  }

  function handleMouseUp() {
    draggingId = null;
  }
</script>

<svelte:window on:mousemove={handleMouseMove} on:mouseup={handleMouseUp} />

<div class="plan-container" bind:this={container}>
  <img src={planUrl} alt="Plan" class="plan-image" draggable="false" />

  {#each warnings as warning (warning.id)}
    <button
      class="warning-marker"
      class:dragging={draggingId === warning.id}
      style="left: {warning.x}%; top: {warning.y}%;"
      on:mousedown={(e) => handleMouseDown(e, warning.id)}
      on:click={() => { if (!hasMoved) onWarningClick(warning); }}
    >
      {warning.icon}
    </button>
  {/each}
</div>

<style>
  .plan-container {
    position: relative;
    display: inline-block;
    width: 100%;
    background: white;
    border-radius: 12px;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
    overflow: hidden;
    border: 1px solid #e2e8f0;
  }

  .plan-image {
    display: block;
    width: 100%;
    height: auto;
    opacity: 0.9; /* Makes it feel more like a technical drawing */
  }

  .warning-marker {
    position: absolute;
    transform: translate(-50%, -50%);
    background: #fff;
    border: 2px solid #000;
    border-radius: 8px; /* Square with rounded corners looks more modern */
    font-size: 1.4rem;
    cursor: move;
    width: 42px;
    height: 42px;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    transition: all 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
  }

  .warning-marker:hover {
    scale: 1.1;
    box-shadow: 0 10px 15px rgba(0,0,0,0.2);
    border-color: #3182ce; /* Luxonis-style accent blue */
  }

  .warning-marker.dragging {
    scale: 1.2;
    opacity: 0.9;
    background: #f7fafc;
    border-style: dashed;
  }
</style>