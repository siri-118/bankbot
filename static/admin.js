// static/js/admin.js
async function postJSON(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  });
  return res;
}

document.addEventListener('DOMContentLoaded', ()=> {
  const clearBtn = document.getElementById('clear-logs-btn');
  if (clearBtn) {
    clearBtn.addEventListener('click', async () => {
      if (!confirm('Delete all logs? This cannot be undone.')) return;
      const res = await fetch('/admin/clear_logs', {method:'POST'});
      const j = await res.json();
      if (j.status === 'ok') location.reload();
      else alert('Error clearing logs');
    });
  }

  const addFaqForm = document.getElementById('add-faq-form');
  if (addFaqForm) {
    addFaqForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const fd = new FormData(addFaqForm);
      const res = await fetch('/admin/add_faq', {method:'POST', body: fd});
      if (res.ok) {
        alert('FAQ added'); addFaqForm.reset(); // optionally refresh FAQ list
      } else {
        const j = await res.json().catch(()=>({}));
        alert('Error: ' + (j.msg || res.statusText));
      }
    });
  }

  const exportBtn = document.getElementById('export-faqs');
  if (exportBtn) {
    exportBtn.addEventListener('click', async () => {
      const res = await fetch('/admin/export_faqs');
      if (!res.ok) { alert('Failed to export'); return; }
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'faqs.json'; a.click();
      URL.revokeObjectURL(url);
    });
  }

  const importBtn = document.getElementById('import-faqs-btn');
  if (importBtn) {
    importBtn.addEventListener('click', async () => {
      const input = document.getElementById('faq-import-file');
      if (!input.files || !input.files.length) { alert('Select a JSON file'); return; }
      const file = input.files[0];
      const text = await file.text();
      let json;
      try { json = JSON.parse(text); } catch (err) { alert('Invalid JSON'); return; }
      const res = await fetch('/admin/import_faqs', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(json)
      });
      if (res.ok) { alert('Imported successfully'); location.reload(); } else { alert('Import failed'); }
    });
  }

  // Filters for recent logs (client-side)
  const filterKind = document.getElementById('filter-kind');
  const filterSuccess = document.getElementById('filter-success');
  const searchUser = document.getElementById('search-user');

  function applyFilters(){
    const rows = document.querySelectorAll('#recent-logs-body tr');
    const kindVal = filterKind ? filterKind.value.toLowerCase() : '';
    const successVal = filterSuccess ? filterSuccess.value.toLowerCase() : '';
    const searchVal = searchUser ? searchUser.value.toLowerCase() : '';
    rows.forEach(r=>{
      const kind = r.querySelector('td:nth-child(2)').innerText.toLowerCase();
      const user = r.querySelector('td:nth-child(3)').innerText.toLowerCase();
      const success = r.querySelector('td:nth-child(4)').innerText.toLowerCase();
      let show = true;
      if (kindVal && !kind.includes(kindVal)) show=false;
      if (successVal && !success.includes(successVal)) show=false;
      if (searchVal && !user.includes(searchVal)) show=false;
      r.style.display = show ? '' : 'none';
    });
  }
  [filterKind, filterSuccess, searchUser].forEach(el=>{ if(el) el.addEventListener('input', applyFilters); });

  // Chart render
  async function renderChart(){
    try {
      const res = await fetch('/admin/chart_data');
      const j = await res.json();
      const ctx = document.getElementById('faqChart').getContext('2d');
      new Chart(ctx, {
        type: 'bar',
        data: {
          labels: j.labels || [],
          datasets: [{
            label: 'Questions asked',
            data: j.values || [],
            borderWidth: 1
          }]
        },
        options: {
          scales: { y: { beginAtZero: true } },
          plugins: { legend: { display: true } }
        }
      });
    } catch (err) {
      console.error('Chart load failed', err);
    }
  }
  renderChart();
});