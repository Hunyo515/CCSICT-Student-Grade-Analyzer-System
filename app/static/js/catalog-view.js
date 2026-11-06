const yearButtons = [...document.querySelectorAll('[data-year]')];
const search = document.querySelector('#catalog-search');
let chosen = yearButtons[0]?.dataset.year;
function updateCatalog() {
  const query = search.value.trim().toLowerCase();
  let matches = 0;
  for (const group of document.querySelectorAll('.curriculum-year')) {
    let groupMatches = 0;
    for (const semester of group.querySelectorAll('.curriculum-semester')) {
      let count = 0;
      for (const row of semester.querySelectorAll('tbody tr')) {
        row.hidden = ![row.cells[0],row.cells[1]].some(cell => cell.textContent.toLowerCase().includes(query));
        if (!row.hidden) count++;
      }
      groupMatches += count;
      semester.hidden = count === 0;
      semester.querySelector('tfoot').hidden = Boolean(query);
      if (query && count) {
        if (!semester.hasAttribute('data-before-search')) semester.dataset.beforeSearch = String(semester.open);
        semester.open = true;
      } else if (!query && semester.hasAttribute('data-before-search')) {
        semester.open = semester.dataset.beforeSearch === 'true';
        delete semester.dataset.beforeSearch;
      }
    }
    group.hidden = !groupMatches || (!query && group.dataset.group !== chosen);
    if (!group.hidden) matches += groupMatches;
  }
  yearButtons.forEach(button => button.setAttribute('aria-pressed', String(!query && button.dataset.year === chosen)));
  document.querySelector('#catalog-empty').hidden = !query || matches > 0;
}
yearButtons.forEach(button => button.addEventListener('click', () => {
  chosen = button.dataset.year;
  search.value = '';
  updateCatalog();
}));
search.addEventListener('input', updateCatalog);
updateCatalog();
