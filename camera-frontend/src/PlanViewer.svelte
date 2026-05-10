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
    border: 1px solid #ccc;
    background: #eee;
    user-select: none;
    overflow: hidden;
  }
  .plan-image { display: block; width: 100%; height: auto; }
  .warning-marker {
    position: absolute;
    transform: translate(-50%, -50%);
    background: white;
    border: 2px solid #333;
    border-radius: 50%;
    font-size: 1.5rem;
    cursor: move;
    padding: 5px;
    z-index: 10;
    line-height: 1;
    transition: scale 0.1s;
  }
  .warning-marker.dragging { scale: 1.3; z-index: 100; border-color: #007bff; }
</style>