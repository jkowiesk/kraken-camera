<script>
  import { onMount } from 'svelte';
  import PlanViewer from './PlanViewer.svelte';
  import WarningModal from './WarningModal.svelte';

  let selectedWarning = null;
  let warnings = [
  {
    "id": 1,
    "x": 41.30244700155129,
    "y": 44.334582161485955,
    "icon": "⚠️",
    "title": "Missing Signage",
    "issue": "Missing sign to toilet. Place it in direction from room 4.",
    "fix": "Install a standard directional toilet sign.",
    "imageUrl": "/travolta_tlo.jpg",
    "modalX": 100,
    "modalY": 100
  },
  {
    "id": 2,
    "x": 55.72552373225174,
    "y": 24.803929062805956,
    "icon": "♿🚫",
    "title": "Access Restricted",
    "issue": "Access not possible via wheelchair due to stairs.",
    "fix": "A ramp or lift installation is required.",
    "imageUrl": "/schody.jpg",
    "modalX": 500,
    "modalY": 100
  }
];

  onMount(() => {
    const saved = localStorage.getItem('plan_state');
    if (saved) warnings = JSON.parse(saved);
  });

  $: {
    localStorage.setItem('plan_state', JSON.stringify(warnings));
  }

  // --- NEW EXPORT FUNCTION ---
  function exportConfig() {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(warnings, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", "luxonis_plan_config.json");
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  }

  function updateIconPosition(id, newX, newY) {
    warnings = warnings.map(w => w.id === id ? { ...w, x: newX, y: newY } : w);
  }

  function updateModalPosition(id, mx, my) {
    warnings = warnings.map(w => w.id === id ? { ...w, modalX: mx, modalY: my } : w);
  }
</script>

<main>
  <header>
    <div class="brand">
      <h1>InfoFinder</h1>
      <span class="divider">|</span>
      <h2>Plan Inspector</h2>
    </div>
    <div class="controls">
      <button class="export-btn" on:click={exportConfig}>Export JSON</button>
    </div>
  </header>

  <PlanViewer
    planUrl="/plan.svg"
    {warnings}
    onWarningClick={(w) => selectedWarning = w}
    onPositionUpdate={updateIconPosition}
  />

  {#if selectedWarning}
    <WarningModal
      warning={warnings.find(w => w.id === selectedWarning.id)}
      onClose={() => selectedWarning = null}
      onPositionChange={updateModalPosition}
    />
  {/if}
</main>

<style>
  :global(body) {
    margin: 0;
    background-color: #f8fafc;
    font-family: 'Inter', sans-serif;
  }

  main {
    max-width: 1200px;
    margin: 0 auto;
    padding: 30px;
  }

  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 30px;
    padding-bottom: 15px;
    border-bottom: 1px solid #e2e8f0;
  }

  .brand { display: flex; align-items: center; gap: 12px; }

  h1 { font-size: 1.2rem; font-weight: 800; text-transform: uppercase; margin: 0; }
  h2 { font-size: 1.1rem; font-weight: 400; color: #64748b; margin: 0; }
  .divider { color: #cbd5e1; font-weight: 200; }

  .controls { display: flex; gap: 10px; }

  button {
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }

  .export-btn {
    background: #000;
    color: #fff;
    border: none;
  }

  .export-btn:hover { background: #333; }

  .reset-btn {
    background: #fff;
    color: #ef4444;
    border: 1px solid #fee2e2;
  }

  .reset-btn:hover { background: #fef2f2; }
</style>