<script>
  import { onMount } from 'svelte';
  import PlanViewer from './PlanViewer.svelte';
  import WarningModal from './WarningModal.svelte';

  let selectedWarning = null;

  let warnings = [
    {
      id: 1,
      x: 25,
      y: 40,
      icon: '⚠️',
      title: 'Missing Signage',
      issue: 'Missing sign to toilet. Place it in direction from room 4.',
      fix: 'Install a standard directional toilet sign.',
      imageUrl: '/travolta_tlo.jpg', // Changed .png to .jpg
      modalX: 100,
      modalY: 100
    },
    {
      id: 2,
      x: 75,
      y: 65,
      icon: '♿🚫',
      title: 'Access Restricted',
      issue: 'Access not possible via wheelchair due to stairs.',
      fix: 'A ramp or lift installation is required.',
      imageUrl: '/schody.jpg', // Changed .png to .jpg
      modalX: 500,
      modalY: 100
    }
  ];

  // Load from LocalStorage on mount
  onMount(() => {
    const saved = localStorage.getItem('plan_state');
    if (saved) {
      try {
        warnings = JSON.parse(saved);
      } catch (e) {
        console.error("Failed to parse saved state", e);
      }
    }
  });

  // AUTO-SAVE: Reactive statement saves whenever 'warnings' changes
  $: {
    localStorage.setItem('plan_state', JSON.stringify(warnings));
  }

  function updateIconPosition(id, newX, newY) {
    warnings = warnings.map(w => w.id === id ? { ...w, x: newX, y: newY } : w);
  }

  function updateModalPosition(id, mx, my) {
    warnings = warnings.map(w => w.id === id ? { ...w, modalX: mx, modalY: my } : w);
  }

  function resetData() {
    localStorage.removeItem('plan_state');
    window.location.reload();
  }
</script>

<main>
  <header>
    <h1>Randstad Building Plan</h1>
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
  main { max-width: 1200px; margin: 0 auto; padding: 20px; font-family: sans-serif; }
  header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
  .status { font-size: 0.8rem; color: #666; margin-right: 10px; }
  button { cursor: pointer; padding: 5px 10px; }
</style>